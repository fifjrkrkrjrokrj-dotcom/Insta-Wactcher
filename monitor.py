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


async def check_account(username: str) -> tuple[AccountStatus, str]:
    """
    Check an Instagram account's status.

    Detection priority:
      1. Direct ban/suspension text on the page
      2. "Not found" / 404
      3. Page title analysis (profile title vs generic title)
      4. Verified badge check
      5. Default: active
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

                # 1. Explicit ban / suspension text
                for phrase in BAN_PHRASES:
                    if phrase in lowered:
                        logger.info(
                            "Ban phrase matched for %s: %r", username, phrase
                        )
                        return AccountStatus.SUSPENDED, f"Detected: {phrase}"

                # 2. Not found / 404
                for phrase in NOT_FOUND_PHRASES:
                    if phrase in lowered:
                        return AccountStatus.NOT_FOUND, "Page not found"

                if resp.status == 404:
                    return AccountStatus.NOT_FOUND, "Page returned 404"

                # 3. Page title analysis
                title = _extract_title(text)
                if title and not _title_has_username(title, username):
                    logger.info(
                        "Profile not loaded for %s (title=%r)",
                        username,
                        title[:80],
                    )
                    return AccountStatus.SUSPENDED, (
                        f"Profile not loaded (title: {title[:80]})"
                    )

                # 4. Verified badge
                if re.search(r'"is_verified"\s*:\s*true', lowered):
                    return AccountStatus.VERIFIED, "Account is verified"

                return AccountStatus.ACTIVE, "Account appears active"

        except asyncio.TimeoutError:
            return AccountStatus.ERROR, "Request timed out"
        except aiohttp.ClientError as e:
            return AccountStatus.ERROR, f"Connection error: {e}"
        except Exception as e:
            return AccountStatus.ERROR, str(e)


def _extract_title(html: str) -> str | None:
    match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def _title_has_username(title: str, username: str) -> bool:
    """
    Check whether the HTML <title> indicates a real profile loaded.

    A normal profile title looks like:
        "User (@user) • Instagram photos and videos"

    Error / restriction pages have a generic title like:
        "Instagram" or "Instagram • Help Center"
    """
    lower_title = title.lower()
    lower_user = username.lower()

    # Direct username hit
    if lower_user in lower_title:
        return True

    # Title contains @ — likely a profile with a different canonical name
    if "@" in lower_title:
        return True

    # Instagram normalises dots out of usernames, so 'user.name'
    # redirects to the canonical profile (title has 'username' not 'user.name').
    if "." in lower_user and lower_user.replace(".", "") in lower_title:
        return True

    return False
