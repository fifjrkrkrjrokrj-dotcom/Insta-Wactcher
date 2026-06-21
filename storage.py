import json
import os
from datetime import datetime

DATA_FILE = "monitored_accounts.json"


def _ensure_user(data: dict, chat_id: str) -> dict:
    if chat_id not in data:
        data[chat_id] = {"accounts": {}, "settings": {}}
    user = data[chat_id]
    if "accounts" not in user:
        user["accounts"] = {}
    if "settings" not in user:
        user["settings"] = {}
    return user


def load() -> dict:
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save(data: dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_accounts(chat_id: str) -> dict:
    data = load()
    user = data.get(chat_id, {})
    return user.get("accounts", {})


def update_account_status(chat_id: str, username: str, status: str) -> None:
    data = load()
    user = _ensure_user(data, chat_id)
    user["accounts"][username] = {
        "status": status,
        "last_checked": datetime.now().isoformat(),
    }
    save(data)


def remove_account(chat_id: str, username: str) -> bool:
    data = load()
    user = data.get(chat_id)
    if user and username in user.get("accounts", {}):
        del user["accounts"][username]
        save(data)
        return True
    return False


def get_setting(chat_id: str, key: str, default=None):
    data = load()
    user = data.get(chat_id, {})
    return user.get("settings", {}).get(key, default)


def set_setting(chat_id: str, key: str, value) -> None:
    data = load()
    user = _ensure_user(data, chat_id)
    user["settings"][key] = value
    save(data)
