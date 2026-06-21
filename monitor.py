import asyncio
import re
from enum import Enum

import aiohttp


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


async def check_account(username: str) -> tuple[AccountStatus, str]:
    """Check an Instagram account's status. Returns (status, detail)."""
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

                if "this account has been suspended" in lowered:
                    return AccountStatus.SUSPENDED, "Account has been suspended by Instagram"
                if "temporarily banned" in lowered or "this account is temporarily restricted" in lowered:
                    return AccountStatus.BANNED, "Account is temporarily restricted"
                if "sorry, this page isn't available" in lowered:
                    return AccountStatus.NOT_FOUND, "Page not found - account may not exist"
                if resp.status == 404:
                    return AccountStatus.NOT_FOUND, "Page returned 404"

                if re.search(r'"is_verified"\s*:\s*true', lowered):
                    return AccountStatus.VERIFIED, "Account is verified"

                return AccountStatus.ACTIVE, "Account appears active"
        except asyncio.TimeoutError:
            return AccountStatus.ERROR, "Request timed out"
        except aiohttp.ClientError as e:
            return AccountStatus.ERROR, f"Connection error: {e}"
        except Exception as e:
            return AccountStatus.ERROR, str(e)
