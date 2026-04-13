import logging

from telegram import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeDefault, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot.config import BOT_TOKEN, DATABASE_URL
from bot.database import Database
from bot.handlers.debt import build_debt_conversation
from bot.handlers.debts import debts_handler
from bot.handlers.help import help_handler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def track_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Record every user + chat interaction so the members table stays current."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or user.is_bot or not chat:
        return
    db: Database = context.bot_data["db"]
    await db.upsert_user(user.id, user.username, user.full_name)
    await db.upsert_chat(chat.id, getattr(chat, "title", None) or chat.full_name)
    await db.upsert_chat_member(chat.id, user.id)


async def import_chat_admins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    When the bot is added to a group, immediately import all current admins.
    This seeds the members table so @mentions work without waiting for messages.
    """
    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        return
    db: Database = context.bot_data["db"]
    try:
        await db.upsert_chat(chat.id, chat.title)
        admins = await context.bot.get_chat_administrators(chat.id)
        for admin in admins:
            u = admin.user
            if not u.is_bot:
                await db.upsert_user(u.id, u.username, u.full_name)
                await db.upsert_chat_member(chat.id, u.id)
        logger.info("Imported %d admins for chat %d", len(admins), chat.id)
    except Exception:
        logger.exception("Failed to import admins for chat %d", chat.id)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log all unhandled exceptions so they appear in Railway logs."""
    logger.error("Unhandled exception", exc_info=context.error)


async def expired_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Catch button presses for conversations that have already ended/timed out."""
    query = update.callback_query
    await query.answer(
        "Время вышло. Введи команду заново.", show_alert=True
    )


async def post_init(application: Application) -> None:
    db = Database(DATABASE_URL)
    await db.init()
    application.bot_data["db"] = db
    logger.info("Database initialised.")

    commands = [
        BotCommand("debt",  "Записать долг или платёж: /debt 150 [валюта] [@user]"),
        BotCommand("debts", "Показать текущие долги"),
        BotCommand("help",  "Справка по командам"),
    ]
    try:
        await application.bot.set_my_commands(commands, scope=BotCommandScopeDefault())
        await application.bot.set_my_commands(commands, scope=BotCommandScopeAllGroupChats())
        logger.info("Bot commands registered.")
    except Exception:
        logger.exception("Failed to register bot commands.")


async def post_shutdown(application: Application) -> None:
    db: Database | None = application.bot_data.get("db")
    if db:
        await db.close()
        logger.info("Database connection closed.")


def main() -> None:
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # ConversationHandlers must be registered before plain CommandHandlers
    app.add_handler(build_debt_conversation())

    # Simple one-shot commands
    app.add_handler(CommandHandler("debts", debts_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("start", help_handler))

    # Catch expired inline button presses (runs after ConversationHandlers)
    app.add_handler(CallbackQueryHandler(expired_callback))

    app.add_error_handler(error_handler)

    # Import admins when bot is added to a group
    app.add_handler(ChatMemberHandler(import_chat_admins, ChatMemberHandler.MY_CHAT_MEMBER))

    # Track every user who sends a message (handler group 1 always fires)
    app.add_handler(MessageHandler(filters.ALL, track_user), group=1)

    logger.info("Bot starting…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
