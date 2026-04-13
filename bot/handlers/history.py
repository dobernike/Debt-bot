from telegram import Update
from telegram.ext import ContextTypes

from bot.database import Database
from bot.formatting import format_global_history, format_history


async def history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.bot_data["db"]
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        rows = await db.get_transaction_history_for_user(user.id, limit=10)
        user_ids = {int(r["debtor_id"]) for r in rows} | {int(r["creditor_id"]) for r in rows}
        users = await db.get_users_by_ids(list(user_ids))
        user_lookup = {u["user_id"]: u for u in users}
        text = "📋 История (последние 10)\n\n" + format_global_history(rows, user_lookup)
        await update.message.reply_text(text, parse_mode="HTML")
    else:
        rows = await db.get_transaction_history(chat.id, limit=10)
        members = await db.get_chat_members(chat.id)
        user_lookup = {m["user_id"]: m for m in members}
        text = "📋 История (последние 10)\n\n" + format_history(rows, user_lookup)
        await update.message.reply_text(text)
