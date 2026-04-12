from telegram import Update
from telegram.ext import ContextTypes

from bot.formatting import format_help


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(format_help(), parse_mode="MarkdownV2")
