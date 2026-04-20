from telegram import Update
from telegram.ext import ContextTypes

from bot.currency import is_valid_currency, normalize_currency, suggest_currency
from bot.database import Database


async def currency_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.bot_data["db"]
    chat = update.effective_chat
    user = update.effective_user
    is_private = chat.type == "private"

    args = context.args or []

    if not args:
        # Show current default
        if is_private:
            cur = await db.get_user_default_currency(user.id)
            await update.message.reply_text(f"Твоя дефолтная валюта: <b>{cur}</b>", parse_mode="HTML")
        else:
            cur = await db.get_chat_default_currency(chat.id)
            await update.message.reply_text(f"Дефолтная валюта чата: <b>{cur}</b>", parse_mode="HTML")
        return

    code = args[0]

    if is_valid_currency(code):
        currency = normalize_currency(code)
    else:
        suggested = suggest_currency(code)
        if suggested:
            currency = suggested
        else:
            await update.message.reply_text(
                f'Неизвестная валюта "{code}". '
                "Используй код ISO 4217 (например RUB, USD, EUR) или русское название (руб, доллар)."
            )
            return

    if is_private:
        await db.set_user_default_currency(user.id, currency)
        await update.message.reply_text(f"Твоя дефолтная валюта: <b>{currency}</b>", parse_mode="HTML")
    else:
        await db.set_chat_default_currency(chat.id, currency)
        await update.message.reply_text(f"Дефолтная валюта чата: <b>{currency}</b>", parse_mode="HTML")
