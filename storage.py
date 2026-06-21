import os
from datetime import datetime

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
_client = AsyncIOMotorClient(MONGODB_URI)
_db = _client.insta_monitor
collection = _db.accounts


async def load() -> dict:
    result = {}
    async for doc in collection.find():
        result[doc["chat_id"]] = {
            "accounts": doc.get("accounts", {}),
            "settings": doc.get("settings", {}),
        }
    return result


async def get_accounts(chat_id: str) -> dict:
    doc = await collection.find_one({"chat_id": chat_id})
    return doc.get("accounts", {}) if doc else {}


async def update_account_status(chat_id: str, username: str, status: str) -> None:
    await collection.update_one(
        {"chat_id": chat_id},
        {
            "$set": {
                f"accounts.{username}": {
                    "status": status,
                    "last_checked": datetime.now().isoformat(),
                }
            }
        },
        upsert=True,
    )


async def remove_account(chat_id: str, username: str) -> bool:
    doc = await collection.find_one({"chat_id": chat_id})
    if doc and username in doc.get("accounts", {}):
        await collection.update_one(
            {"chat_id": chat_id},
            {"$unset": {f"accounts.{username}": ""}},
        )
        doc = await collection.find_one({"chat_id": chat_id})
        if doc and not doc.get("accounts"):
            await collection.delete_one({"chat_id": chat_id})
        return True
    return False


async def get_setting(chat_id: str, key: str, default=None):
    doc = await collection.find_one({"chat_id": chat_id})
    if doc:
        return doc.get("settings", {}).get(key, default)
    return default


async def set_setting(chat_id: str, key: str, value) -> None:
    await collection.update_one(
        {"chat_id": chat_id},
        {"$set": {f"settings.{key}": value}},
        upsert=True,
    )
