"""Shared utilities used by both debt and settle handlers."""
from __future__ import annotations

import logging

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

from bot.database import Database
from bot.formatting import display_name

logger = logging.getLogger(__name__)


async def resolve_user_by_username(
    bot: Bot,
    db: Database,
    username: str,
    chat_id: int,
) -> dict | None:
    """
    Look up a user by @username.

    1. Check the local DB first (populated by track_user handler).
    2. Fall back to Telegram API: get_chat("@username") to resolve the
       user_id, then verify they are actually a member of the chat.

    Returns a dict with user_id / username / full_name, or None if not found.
    """
    clean = username.lstrip("@")

    # Fast path: already in DB
    member = await db.get_user_by_username(clean, chat_id)
    if member:
        return member

    # Slow path: ask Telegram API
    try:
        chat = await bot.get_chat(f"@{clean}")
        user_id = chat.id
        full_name = chat.full_name or clean
        uname = chat.username
    except TelegramError:
        return None

    # Confirm the user is actually in this chat
    try:
        await bot.get_chat_member(chat_id, user_id)
    except TelegramError:
        return None

    # Persist so next lookup is instant
    await db.upsert_user(user_id, uname, full_name)
    await db.upsert_chat_member(chat_id, user_id)

    return {"user_id": user_id, "username": uname, "full_name": full_name}


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
                        "Первый аргумент должен быть числом, например /debt 150"
                    )

    return amount, currency_str, username
