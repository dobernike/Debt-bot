from telegram import Update
from telegram.ext import ContextTypes

from bot.database import Database
from bot.formatting import format_history


async def history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat

    if chat.type == "private":
        await update.message.reply_text("Команда работает только в групповых чатах.")
        return

    db: Database = context.bot_data["db"]
    rows = await db.get_transaction_history(chat.id, limit=10)
    members = await db.get_chat_members(chat.id)
    user_lookup = {m["user_id"]: m for m in members}
    text = "📋 История (последние 10)\n\n" + format_history(rows, user_lookup)
    await update.message.reply_text(text)
