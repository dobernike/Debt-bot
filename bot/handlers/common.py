"""Shared utilities used by both debt and settle handlers."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.database import Database
from bot.formatting import display_name


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

    for token in args:
        if token.startswith("@"):
            username = token.lstrip("@")
        else:
            try:
                value = float(token.replace(",", "."))
                if amount is None:
                    amount = value
                else:
                    raise ValueError(f"Unexpected extra number: {token!r}")
            except ValueError:
                if currency_str is None and amount is not None:
                    # Treat as currency only after we already have an amount
                    currency_str = token
                elif currency_str is None and amount is None:
                    raise ValueError(
                        "First argument must be a number, e.g. /debt 150"
                    )

    return amount, currency_str, username
