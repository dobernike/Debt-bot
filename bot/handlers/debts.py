from telegram import Update
from telegram.ext import ContextTypes

from bot.database import Database
from bot.formatting import format_debt_summary, format_global_debt_summary


async def debts_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.bot_data["db"]
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        # Private chat: show all the user's debts across every group
        debts = await db.get_all_debts_for_user(user.id)
        user_ids = {int(d["debtor_id"]) for d in debts} | {int(d["creditor_id"]) for d in debts}
        users = await db.get_users_by_ids(list(user_ids))
        user_lookup = {u["user_id"]: u for u in users}
        summary = format_global_debt_summary(debts, user_lookup, viewer_id=user.id)
        await update.message.reply_text(summary, parse_mode="HTML")
    else:
        # Group chat: show only this group's debts
        active_debts = await db.get_active_debts(chat.id)
        members = await db.get_chat_members(chat.id)
        user_lookup = {m["user_id"]: m for m in members}
        summary = format_debt_summary(active_debts, user_lookup)
        await update.message.reply_text(summary)
