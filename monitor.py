import asyncio
import logging
import re
from enum import Enum

import aiohttp

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


# ── Page-type detection lists ────────────────────────────

LOGIN_PHRASES = [
    "log in to instagram",
    "log in to see",
    "please log in",
    "sign in to instagram",
    "login",
    "log in",
]

CHALLENGE_PHRASES = [
    "please wait a few minutes",
    "too many requests",
    "unusual activity",
    "challenge required",
    "blocked",
    "captcha",
    "security check",
    "confirm you're not a robot",
    "we've detected unusual activity",
    "we limit how often",
]

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

PROFILE_SIGNALS = [
    '"username"',
    '"full_name"',
    '"biography"',
    '"profile_pic_url"',
    '"edge_owner_to_timeline_media"',
    '"is_verified"',
    '"followed_by"',
    '"profile_page"',
    'og:title',
    'og:description',
    'instagram://user',
]


async def check_account(username: str) -> tuple[AccountStatus, str]:
    """Check an Instagram account's status.

    Detection flow:
      1. Login / challenge wall  → ERROR
      2. Ban / suspension text   → SUSPENDED
      3. Not found / 404         → NOT_FOUND
      4. Profile data present?   → continue; else SUSPENDED
      5. Verified badge          → VERIFIED
      6. Default                 → ACTIVE
    """
    url = f"https://www.instagram.com/{username}/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.5",
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                url, headers=headers, timeout=15, allow_redirects=True
            ) as resp:
                text = await resp.text()
                lowered = text.lower()

                # 1. Login / challenge walls → we can't verify anything
                for phrase in LOGIN_PHRASES:
                    if phrase in lowered:
                        logger.info("Login wall for %s", username)
                        return AccountStatus.ERROR, "Login required to view profile"

                for phrase in CHALLENGE_PHRASES:
                    if phrase in lowered:
                        logger.info("Challenge/rate-limit for %s", username)
                        return AccountStatus.ERROR, "Rate-limited or challenge required"

                # 2. Ban / suspension text
                for phrase in BAN_PHRASES:
                    if phrase in lowered:
                        logger.info("Ban phrase for %s: %r", username, phrase)
                        return AccountStatus.SUSPENDED, f"Detected: {phrase}"

                # 3. Not found / 404
                for phrase in NOT_FOUND_PHRASES:
                    if phrase in lowered:
                        return AccountStatus.NOT_FOUND, "Page not found"

                if resp.status == 404:
                    return AccountStatus.NOT_FOUND, "Page returned 404"

                # 4. Multi-signal profile detection
                title = _extract_title(text)
                if not _profile_loaded(text, lowered, title, username):
                    logger.info(
                        "No profile data for %s (title=%r, status=%d)",
                        username,
                        title[:80] if title else None,
                        resp.status,
                    )
                    return AccountStatus.SUSPENDED, "Account restricted or page format unrecognised"

                # 5. Verified badge
                if re.search(r'"is_verified"\s*:\s*true', lowered):
                    return AccountStatus.VERIFIED, "Account is verified"

                return AccountStatus.ACTIVE, "Account appears active"

        except asyncio.TimeoutError:
            return AccountStatus.ERROR, "Request timed out"
        except aiohttp.ClientError as e:
            return AccountStatus.ERROR, f"Connection error: {e}"
        except Exception as e:
            return AccountStatus.ERROR, str(e)


# ── Helpers ──────────────────────────────────────────────

def _extract_title(html: str) -> str | None:
    match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else None


def _title_has_username(title: str, username: str) -> bool:
    """Check whether the page <title> belongs to a real profile."""
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
    """Return True if the page actually contains profile data for *username*."""

    # Signal A — title contains the username or an @-handle
    if title and _title_has_username(title, username):
        return True

    # Signal B — username appears in the page body
    if username.lower() in lowered:
        return True

    # Signal C — common profile JSON keys are present
    for sig in PROFILE_SIGNALS:
        if sig in lowered:
            return True

    # Signal D — the HTTP response has Instagram profile meta
    if "profile" in lowered and ("instagram" in lowered or username.lower() in lowered):
        return True

    return False
