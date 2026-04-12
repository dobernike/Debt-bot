from telegram import Update
from telegram.ext import ContextTypes

from bot.database import Database
from bot.formatting import format_debt_summary


async def debts_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.bot_data["db"]
    chat_id = update.effective_chat.id

    active_debts = await db.get_active_debts(chat_id)
    members = await db.get_chat_members(chat_id)
    user_lookup = {m["user_id"]: m for m in members}

    summary = format_debt_summary(active_debts, user_lookup)
    await update.message.reply_text(summary)
