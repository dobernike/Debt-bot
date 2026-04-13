"""Shared utilities used by both debt and settle handlers."""
from __future__ import annotations

import re

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from bot.database import Database
from bot.formatting import display_name

# Only allow digits, spaces, and basic arithmetic operators (+, -, *, /, ., parentheses)
_SAFE_EXPR_RE = re.compile(r'^[\d\s\+\-\*\/\.\(\)]+$')


def _try_parse_number(token: str) -> float | None:
    """
    Try to parse a token as a number or a safe arithmetic expression.
    Returns the float value, or None if the token is not numeric/math.
    Raises ValueError if the expression looks numeric but is invalid.
    """
    normalized = token.replace(",", ".")
    # Plain float first
    try:
        return float(normalized)
    except ValueError:
        pass
    # Math expression: only allow safe characters
    if _SAFE_EXPR_RE.match(normalized):
        try:
            result = eval(normalized, {"__builtins__": {}})  # noqa: S307
            return float(result)
        except Exception:
            return None
    return None


async def build_member_keyboard(
    db: Database,
    chat_id: int,
    exclude_user_id: int,
    prefix: str = "recipient",
) -> InlineKeyboardMarkup | None:
    """
    Build an inline keyboard listing all known chat members except the sender.
    Returns None if no candidates exist.
    """
    members = await db.get_chat_members(chat_id)
    candidates = [m for m in members if m["user_id"] != exclude_user_id]
    if not candidates:
        return None
    buttons = [
        [
            InlineKeyboardButton(
                display_name(m),
                callback_data=f"{prefix}:{m['user_id']}",
            )
        ]
        for m in candidates
    ]
    return InlineKeyboardMarkup(buttons)


def parse_amount_currency_username(
    args: list[str],
) -> tuple[float | None, str | None, str | None]:
    """
    Loosely parse a list of tokens into (amount, currency_str, username).
    Tokens can be in any order: amount is the first float found,
    username is any token starting with '@', currency is anything else.
    Returns None for each field if not found.
    Raises ValueError if the first non-@ token cannot be parsed as float.
    """
    amount: float | None = None
    currency_str: str | None = None
    username: str | None = None

    # Merge bare sign tokens ("- 300" → "-300", "+ 300" → "+300")
    merged: list[str] = []
    i = 0
    while i < len(args):
        if args[i] in ("-", "+") and i + 1 < len(args) and not args[i + 1].startswith("@"):
            merged.append(args[i] + args[i + 1])
            i += 2
        else:
            merged.append(args[i])
            i += 1

    for token in merged:
        if token.startswith("@"):
            username = token.lstrip("@")
        else:
            value = _try_parse_number(token)
            if value is not None:
                if amount is None:
                    amount = value
                else:
                    raise ValueError(f"Неожиданное число: {token!r}")
            else:
                # Not a number — treat as currency or error
                if currency_str is None and amount is not None:
                    currency_str = token
                elif currency_str is None and amount is None:
                    raise ValueError(
                        "Первый аргумент должен быть числом, например /debt 150"
                    )

    return amount, currency_str, username
