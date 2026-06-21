import asyncio
import logging
import os

from dotenv import load_dotenv
from telethon import TelegramClient, Button, events

from monitor import check_account, AccountStatus
from storage import (
    get_accounts,
    get_setting,
    load,
    remove_account,
    set_setting,
    update_account_status,
)
from ui import (
    account_actions_keyboard,
    account_list_keyboard,
    back_keyboard,
    confirm_remove_keyboard,
    interval_picker_keyboard,
    main_keyboard,
    notification_keyboard,
    settings_keyboard,
    make_cb,
    parse_cb,
    styled_button,
    style_keyboard,
    CB_ADD,
    CB_BACK,
    CB_CANCEL_REMOVE,
    CB_CHECK,
    CB_CHECK_ALL,
    CB_CONFIRM_REMOVE,
    CB_LIST,
    CB_MAIN,
    CB_REMOVE,
    CB_SETTINGS,
    CB_SET_INTERVAL,
    CB_TOGGLE_NOTIFY,
)

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
DEFAULT_INTERVAL = max(5, int(os.getenv("CHECK_INTERVAL_MINUTES", 30)))

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

client = TelegramClient("insta_monitor", API_ID, API_HASH)

STATUS_LABELS = {
    "active": "Active",
    "verified": "Verified",
    "banned": "Temp Banned",
    "suspended": "Suspended",
    "not_found": "Not Found",
    "error": "Error",
}


def fmt_status(username: str, status_value: str, detail: str = "") -> str:
    label = STATUS_LABELS.get(status_value, status_value)
    text = f"@{username} -> {label}"
    if detail:
        text += f"\n{detail}"
    return text


@client.on(events.NewMessage(pattern="/start"))
async def start_cmd(event):
    text = (
        "Instagram Ban Monitor Bot\n\n"
        "Monitor Instagram accounts and get notified when they get "
        "banned, unbanned, or verified.\n\n"
        "Use the buttons below or send a username to add it."
    )
    await event.reply(text, buttons=main_keyboard())


@client.on(events.NewMessage(pattern="/add(?: (.+))?"))
async def add_cmd(event):
    username = event.pattern_match.group(1)
    if not username:
        await event.reply(
            "Send me the Instagram username to monitor:",
            buttons=back_keyboard(),
        )
        return
    username = username.strip().lower()
    chat_id = str(event.chat_id)
    msg = await event.reply(f"Checking @{username}...")
    status, detail = await check_account(username)
    await update_account_status(chat_id, username, status.value)
    text = (
        f"Added @{username} to monitoring.\n"
        f"{fmt_status(username, status.value, detail)}"
    )
    await msg.edit(text, buttons=main_keyboard())


@client.on(events.NewMessage(pattern="/list"))
async def list_cmd(event):
    await send_account_list(event)


@client.on(events.NewMessage(pattern="/remove(?: (.+))?"))
async def remove_cmd(event):
    username = event.pattern_match.group(1)
    if not username:
        await event.reply("Usage: /remove <username>")
        return
    username = username.strip().lower()
    chat_id = str(event.chat_id)
    if await remove_account(chat_id, username):
        await event.reply(f"Removed @{username}.", buttons=main_keyboard())
    else:
        await event.reply(
            f"@{username} not in your list.", buttons=main_keyboard()
        )


@client.on(events.NewMessage)
async def text_fallback(event):
    if event.text.startswith("/"):
        return
    username = event.text.strip().lower()
    chat_id = str(event.chat_id)
    msg = await event.reply(f"Checking @{username}...")
    status, detail = await check_account(username)
    await update_account_status(chat_id, username, status.value)
    text = (
        f"Added @{username} to monitoring.\n"
        f"{fmt_status(username, status.value, detail)}"
    )
    await msg.edit(text, buttons=main_keyboard())


async def send_account_list(event, edit=False):
    chat_id = str(event.chat_id)
    accounts = await get_accounts(chat_id)
    if not accounts:
        text = "No accounts being monitored.\nUse /add or tap Add Account below."
        buttons = main_keyboard()
    else:
        lines = ["Your monitored accounts:\n"]
        for username, info in accounts.items():
            sv = info["status"] if isinstance(info, dict) else info
            lines.append(fmt_status(username, sv))
        text = "\n".join(lines)
        buttons = account_list_keyboard(accounts)
    if edit:
        await event.edit(text, buttons=buttons)
    else:
        await event.respond(text, buttons=buttons)


async def show_settings_panel(event):
    chat_id = str(event.chat_id)
    interval = await get_setting(chat_id, "interval", DEFAULT_INTERVAL)
    notify = await get_setting(chat_id, "notifications", True)
    text = (
        "Settings\n\n"
        f"Check Interval: {interval} minutes\n"
        f"Notifications: {'On' if notify else 'Off'}"
    )
    await event.edit(text, buttons=settings_keyboard(interval, notify))


@client.on(events.CallbackQuery)
async def callback_handler(event):
    action, value = parse_cb(event.data)
    chat_id = str(event.chat_id)

    if action == CB_MAIN:
        text = (
            "Instagram Ban Monitor Bot\n\n"
            "Monitor Instagram accounts and get notified when they get "
            "banned, unbanned, or verified.\n\n"
            "Use the buttons below or send a username to add it."
        )
        await event.edit(text, buttons=main_keyboard())

    elif action == CB_LIST:
        await send_account_list(event, edit=True)

    elif action == CB_ADD:
        await event.edit(
            "Send me the Instagram username to monitor:",
            buttons=back_keyboard(),
        )

    elif action == CB_CHECK_ALL:
        await event.edit("Checking all accounts, please wait...")
        accounts = await get_accounts(chat_id)
        if not accounts:
            await event.edit(
                "No accounts to check.", buttons=main_keyboard()
            )
            return
        results = []
        for username in list(accounts.keys()):
            status, detail = await check_account(username)
            await update_account_status(chat_id, username, status.value)
            results.append(fmt_status(username, status.value, detail))
        await event.edit("\n\n".join(results), buttons=main_keyboard())

    elif action == CB_CHECK:
        if not value:
            return
        status, detail = await check_account(value)
        await update_account_status(chat_id, value, status.value)
        text = fmt_status(value, status.value, detail)
        await event.edit(text, buttons=account_actions_keyboard(value))

    elif action == CB_REMOVE:
        if not value:
            return
        text = f"Remove @{value} from monitoring?"
        await event.edit(text, buttons=confirm_remove_keyboard(value))

    elif action == CB_CONFIRM_REMOVE:
        if not value:
            return
        if await remove_account(chat_id, value):
            await event.edit(
                f"Removed @{value}.", buttons=main_keyboard()
            )
        else:
            await event.edit(
                f"@{value} not found.", buttons=main_keyboard()
            )

    elif action == CB_CANCEL_REMOVE:
        await send_account_list(event, edit=True)

    elif action == CB_SETTINGS:
        await show_settings_panel(event)

    elif action == CB_SET_INTERVAL:
        if value:
            await set_setting(chat_id, "interval", int(value))
            await show_settings_panel(event)
        else:
            current = await get_setting(chat_id, "interval", DEFAULT_INTERVAL)
            await event.edit(
                "Select check interval:",
                buttons=interval_picker_keyboard(current),
            )

    elif action == CB_TOGGLE_NOTIFY:
        current = await get_setting(chat_id, "notifications", True)
        await set_setting(chat_id, "notifications", not current)
        await show_settings_panel(event)


async def periodic_check_loop():
    await client.wait_until_ready()
    logger.info("Periodic checker started")
    while True:
        try:
            data = await load()
            for chat_id_str, user_data in data.items():
                accounts = user_data.get("accounts", {})
                for username, info in list(accounts.items()):
                    last_status = (
                        info["status"]
                        if isinstance(info, dict)
                        else info
                    )
                    new_status, detail = await check_account(username)
                    if new_status.value != last_status:
                        await update_account_status(
                            chat_id_str, username, new_status.value
                        )
                        notify = await get_setting(
                            chat_id_str, "notifications", True
                        )
                        if not notify:
                            continue
                        is_banned = new_status.value in (
                            "banned",
                            "suspended",
                        )
                        was_banned = last_status in ("banned", "suspended")
                        is_verified = new_status.value == "verified"
                        was_verified = last_status == "verified"
                        if is_banned and not was_banned:
                            headline = f"BANNED: @{username}"
                        elif was_banned and not is_banned:
                            headline = f"UNBANNED: @{username}"
                        elif is_verified and not was_verified:
                            headline = f"VERIFIED: @{username}"
                        else:
                            headline = f"Status changed: @{username}"
                        try:
                            await client.send_message(
                                int(chat_id_str),
                                f"{headline}\n"
                                f"New: {STATUS_LABELS.get(new_status.value, new_status.value)}\n"
                                f"{detail}",
                                buttons=notification_keyboard(username),
                            )
                        except Exception:
                            logger.exception(
                                f"Failed to notify {chat_id_str}"
                            )
            sleep_minutes = DEFAULT_INTERVAL
            data = await load()
            for ud in data.values():
                ui = ud.get("settings", {}).get("interval")
                if ui:
                    sleep_minutes = min(sleep_minutes, int(ui))
            await asyncio.sleep(sleep_minutes * 60)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Periodic check error")
            await asyncio.sleep(60)


async def main():
    await client.start(bot_token=TOKEN)
    logger.info("Bot started")
    checker = asyncio.create_task(periodic_check_loop())
    await client.run_until_disconnected()
    checker.cancel()


if __name__ == "__main__":
    client.loop.run_until_complete(main())
