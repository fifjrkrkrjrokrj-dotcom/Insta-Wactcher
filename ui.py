"""
Telethon button styling system with auto-pattern monkeypatch.
Port from Villainaddbot/utils.py — ports styled_button(), style_keyboard(),
and automatic keyboard builders.
"""

import logging
from telethon import Button

logger = logging.getLogger(__name__)

# ── Callback data helpers ────────────────────────────────

CB_DELIM = ":"

def make_cb(action: str, data: str = "") -> bytes:
    if data:
        return f"{action}{CB_DELIM}{data}".encode()
    return action.encode()


def parse_cb(raw: bytes) -> tuple[str, str]:
    decoded = raw.decode()
    if CB_DELIM in decoded:
        action, value = decoded.split(CB_DELIM, 1)
        return action, value
    return decoded, ""


# ── Styled button ────────────────────────────────────────

def styled_button(text: str, callback_data: str, style: str = "primary"):
    """
    Creates an inline button with style support.
    Falls back gracefully for older Telethon versions.
    """
    try:
        return Button.inline(text, data=callback_data, style=style)
    except TypeError:
        btn = Button.inline(text, data=callback_data)
        try:
            btn.style = style
        except AttributeError:
            setattr(btn, "style", style)
        return btn


SMART_STYLES = {
    "destructive": {
        "keywords": [
            "delete", "stop", "cancel", "reject", "remove",
            "block", "danger", "clear",
        ],
        "style": "danger",
    },
    "constructive": {
        "keywords": [
            "start", "approve", "accept", "confirm", "verify",
            "purchase", "unlock", "join", "subscribe",
        ],
        "style": "success",
    },
}


def detect_smart_style(text: str) -> str | None:
    """Detect if button text suggests a destructive or constructive action."""
    lower = text.lower()
    for category in ("destructive", "constructive"):
        for kw in SMART_STYLES[category]["keywords"]:
            if kw in lower:
                return SMART_STYLES[category]["style"]
    return None


def style_keyboard(buttons):
    """
    Automatically styles keyboard buttons in a repeating pattern.

    Pattern: danger (row 0) -> primary (row 1) -> success (row 2) -> repeat

    Smart detection: buttons with destructive keywords stay 'danger',
    constructive keywords stay 'success', overriding the pattern.
    """
    if not buttons:
        return buttons

    was_single = not isinstance(buttons, (list, tuple))
    was_1d = False

    if was_single:
        grid = [[buttons]]
    elif buttons and not isinstance(buttons[0], (list, tuple)):
        was_1d = True
        grid = [list(buttons)]
    else:
        grid = [list(row) for row in buttons]

    styles = ["danger", "primary", "success"]

    for row_idx, row in enumerate(grid):
        pattern_style = styles[row_idx % len(styles)]

        for btn in row:
            if not hasattr(btn, "text"):
                continue

            smart_style = detect_smart_style(btn.text)
            chosen_style = smart_style if smart_style else pattern_style

            try:
                from telethon.tl.types import KeyboardButtonStyle

                icon = None
                existing = getattr(btn, "style", None)
                if existing and hasattr(existing, "icon"):
                    icon = existing.icon

                style_map = {
                    "primary": KeyboardButtonStyle(bg_primary=True, icon=icon),
                    "danger": KeyboardButtonStyle(bg_danger=True, icon=icon),
                    "success": KeyboardButtonStyle(bg_success=True, icon=icon),
                }
                btn.style = style_map.get(chosen_style)
            except (ImportError, AttributeError, TypeError):
                try:
                    btn.style = chosen_style
                except AttributeError:
                    setattr(btn, "style", chosen_style)

    if was_single:
        return grid[0][0]
    if was_1d:
        return grid[0]
    return grid


# ── Callback action constants ────────────────────────────

CB_MAIN = "m"
CB_LIST = "l"
CB_ADD = "a"
CB_CHECK_ALL = "ca"
CB_SETTINGS = "s"
CB_BACK = "b"

CB_CHECK = "c"
CB_REMOVE = "r"
CB_CONFIRM_REMOVE = "rc"
CB_CANCEL_REMOVE = "nr"

CB_SET_INTERVAL = "si"
CB_TOGGLE_NOTIFY = "tn"


# ── Keyboard builders ────────────────────────────────────

def main_keyboard():
    return style_keyboard([
        [
            Button.inline("Add Account", data=make_cb(CB_ADD)),
            Button.inline("My Accounts", data=make_cb(CB_LIST)),
        ],
        [
            Button.inline("Check All Now", data=make_cb(CB_CHECK_ALL)),
            Button.inline("Settings", data=make_cb(CB_SETTINGS)),
        ],
    ])


def back_keyboard(dest: str = CB_MAIN):
    return style_keyboard([[Button.inline("Back", data=make_cb(dest))]])


def account_list_keyboard(accounts: dict):
    buttons = []
    for username in accounts:
        buttons.append([
            Button.inline(f"@{username}", data=make_cb(CB_CHECK, username)),
            styled_button(
                "Remove", make_cb(CB_REMOVE, username), style="danger"
            ),
        ])
    buttons.append([
        Button.inline("Check All", data=make_cb(CB_CHECK_ALL)),
        Button.inline("Main Menu", data=make_cb(CB_MAIN)),
    ])
    return style_keyboard(buttons)


def account_actions_keyboard(username: str):
    return style_keyboard([
        [
            Button.inline("Refresh", data=make_cb(CB_CHECK, username)),
            styled_button(
                "Remove", make_cb(CB_REMOVE, username), style="danger"
            ),
        ],
        [Button.inline("Back to List", data=make_cb(CB_LIST))],
    ])


def confirm_remove_keyboard(username: str):
    return style_keyboard([
        [
            styled_button(
                "Yes, Remove", make_cb(CB_CONFIRM_REMOVE, username),
                style="danger",
            ),
            Button.inline("Cancel", data=make_cb(CB_CANCEL_REMOVE, username)),
        ]
    ])


def settings_keyboard(interval: int, notify: bool):
    return style_keyboard([
        [Button.inline(f"Interval: {interval}m", data=make_cb(CB_SET_INTERVAL))],
        [
            styled_button(
                f"Notifications: {'ON' if notify else 'OFF'}",
                make_cb(CB_TOGGLE_NOTIFY),
                style="success" if notify else "danger",
            )
        ],
        [Button.inline("Main Menu", data=make_cb(CB_MAIN))],
    ])


def notification_keyboard(username: str):
    return style_keyboard([
        [
            styled_button(
                "Remove from Monitor",
                make_cb(CB_REMOVE, username),
                style="danger",
            )
        ],
        [Button.inline("Main Menu", data=make_cb(CB_MAIN))],
    ])


def interval_picker_keyboard(current: int):
    intervals = [15, 30, 60, 120, 240]
    buttons = []
    row = []
    for i, val in enumerate(intervals):
        marker = " ✓" if val == current else ""
        row.append(
            Button.inline(f"{val}m{marker}", data=make_cb(CB_SET_INTERVAL, str(val)))
        )
        if len(row) == 3 or i == len(intervals) - 1:
            buttons.append(row)
            row = []
    buttons.append([Button.inline("Back", data=make_cb(CB_SETTINGS))])
    return style_keyboard(buttons)
