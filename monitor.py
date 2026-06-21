import asyncio
import logging
import os
import re
from enum import Enum

import aiohttp
from instagrapi import Client
from instagrapi.exceptions import ClientError, LoginRequired, UserNotFound

logger = logging.getLogger(__name__)


class AccountStatus(Enum):
    ACTIVE = "active"
    VERIFIED = "verified"
    BANNED = "banned"
    SUSPENDED = "suspended"
    NOT_FOUND = "not_found"
    ERROR = "error"

    def label(self) -> str:
        return {
            "active": "Active",
            "verified": "Verified",
            "banned": "Temporarily Banned",
            "suspended": "Suspended",
            "not_found": "Not Found",
            "error": "Error",
        }[self.value]


# ── Instagram API client (lazy, session-cached) ─────────

INSTA_USER = os.getenv("INSTAGRAM_USERNAME")
INSTA_PASS = os.getenv("INSTAGRAM_PASSWORD")
SESSION_FILE = "insta_session.json"

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is not None:
        return _client

    _client = Client()

    if os.path.exists(SESSION_FILE):
        try:
            _client.load_settings(SESSION_FILE)
            _client.account_info()
            logger.info("Loaded cached Instagram session")
            return _client
        except Exception:
            logger.warning("Session expired, re-logging in")

    if not INSTA_USER or not INSTA_PASS:
        raise RuntimeError(
            "INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD must be set in .env"
        )

    _client.login(INSTA_USER, INSTA_PASS)
    _client.dump_settings(SESSION_FILE)
    logger.info("Instagram logged in, session cached")
    return _client


def _clear_session() -> None:
    global _client
    _client = None
    for f in (SESSION_FILE,):
        if os.path.exists(f):
            os.remove(f)


def _get_http_cookies(client: Client) -> dict[str, str]:
    """Extract a flat cookie dict from an instagrapi client for aiohttp."""
    raw = client.get_settings().get("cookies", {})
    cookies: dict[str, str] = {}
    for key, value in raw.items():
        if isinstance(value, dict):
            cookies[key] = value.get("value", "")
        elif isinstance(value, str):
            cookies[key] = value
    return cookies


# ── HTTP fallback (uses Instagram session cookies) ──────

BAN_PHRASES = [
    "this account has been suspended",
    "this account has been disabled",
    "this account is temporarily restricted",
    "temporarily banned",
    "your account has been disabled",
    "we restrict certain activity",
    "account banned",
    "suspended account",
    "this account has been permanently banned",
    "this account isn't available",
    "account has been banned",
    "restricted account",
]

NOT_FOUND_PHRASES = [
    "sorry, this page isn't available",
    "the link you followed may be broken",
    "this page doesn't exist",
    "the page you requested was not found",
    "page not found",
    "this page isn't available",
]


async def _http_fallback(username: str, client: Client) -> tuple[AccountStatus, str]:
    """Check the Instagram profile page HTML using logged-in session cookies."""
    url = f"https://www.instagram.com/{username}/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.5",
    }
    cookies = _get_http_cookies(client)

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                url, headers=headers, cookies=cookies, timeout=15, allow_redirects=True
            ) as resp:
                text = await resp.text()
                lowered = text.lower()

                for phrase in BAN_PHRASES:
                    if phrase in lowered:
                        return AccountStatus.SUSPENDED, f"Detected: {phrase}"

                for phrase in NOT_FOUND_PHRASES:
                    if phrase in lowered:
                        return AccountStatus.NOT_FOUND, "Page not found"

                if resp.status == 404:
                    return AccountStatus.NOT_FOUND, "Page returned 404"

                title = _extract_title(text)
                profile_ok = _profile_loaded(text, lowered, title, username)

                if not profile_ok:
                    return AccountStatus.SUSPENDED, "Account restricted"

                if re.search(r'"is_verified"\s*:\s*true', lowered):
                    return AccountStatus.VERIFIED, "Account is verified"

                return AccountStatus.ACTIVE, "Account appears active"
        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            return AccountStatus.ERROR, str(e)[:100]


def _extract_title(html: str) -> str | None:
    m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else None


def _title_has_username(title: str, username: str) -> bool:
    lt = title.lower()
    lu = username.lower()
    if lu in lt:
        return True
    if "@" in lt:
        return True
    if "." in lu and lu.replace(".", "") in lt:
        return True
    return False


def _profile_loaded(text: str, lowered: str, title: str | None, username: str) -> bool:
    if title and _title_has_username(title, username):
        return True
    if username.lower() in lowered:
        return True
    for sig in ('"username"', '"full_name"', '"biography"', '"is_verified"',
                '"edge_owner_to_timeline_media"', '"profile_pic_url"', 'og:title',
                'og:description'):
        if sig in lowered:
            return True
    return False


# ── Public check API ────────────────────────────────────

async def check_account(username: str, _retry: bool = True) -> tuple[AccountStatus, str]:
    """Check an Instagram account's status.

    Uses instagrapi (logged-in) API as the primary source.
    Falls back to HTTP profile-page scraping with session cookies.
    """
    client = _get_client()
    loop = asyncio.get_event_loop()

    try:
        user_info = await loop.run_in_executor(
            None, client.user_info_by_username, username
        )
        if user_info.is_verified:
            return AccountStatus.VERIFIED, "Account is verified"
        return AccountStatus.ACTIVE, "Account appears active"
    except UserNotFound:
        return await _http_fallback(username, client)
    except LoginRequired:
        if _retry:
            _clear_session()
            _get_client()
            return await check_account(username, _retry=False)
        return AccountStatus.ERROR, "Login required"
    except ClientError as e:
        msg = str(e).lower()
        if "suspended" in msg or "disabled" in msg or "banned" in msg:
            return AccountStatus.SUSPENDED, str(e)[:100]
        if "rate" in msg or "throttle" in msg or "wait" in msg or "too many" in msg:
            return AccountStatus.ERROR, "Rate limited"
        return AccountStatus.ERROR, str(e)[:100]
    except Exception as e:
        return AccountStatus.ERROR, str(e)[:100]
