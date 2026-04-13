from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
)

from bot.currency import is_valid_currency, normalize_currency, suggest_currency
from bot.database import Database
from bot.formatting import format_debt_summary
from bot.handlers.common import build_member_keyboard, parse_amount_currency_username
from bot.models import DebtRecord, PendingDebtState

# ConversationHandler states
AWAIT_CURRENCY_CONFIRM = 0
AWAIT_RECIPIENT_SELECT = 1


async def _save_and_reply(
    db: Database,
    state: PendingDebtState,
    from_user_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    reply_target,   # Update or CallbackQuery — used to send the response
    edit: bool = False,
) -> None:
    await db.add_debt(
        DebtRecord(
            debtor_id=from_user_id,
            creditor_id=state.creditor_id,
            amount=state.amount,
            currency=state.currency,
            chat_id=state.chat_id,
        )
    )
    active_debts = await db.get_active_debts(state.chat_id)
    members = await db.get_chat_members(state.chat_id)
    user_lookup = {m["user_id"]: m for m in members}
    summary = format_debt_summary(active_debts, user_lookup)
    text = f"Долг записан.\n\n{summary}"

    if edit:
        await reply_target.edit_message_text(text)
    else:
        await reply_target.message.reply_text(text)

    context.user_data.pop("pending_debt", None)


async def debt_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    db: Database = context.bot_data["db"]
    user = update.effective_user
    chat_id = update.effective_chat.id

    # --- Parse arguments ---
    try:
        amount, currency_str, username = parse_amount_currency_username(
            context.args or []
        )
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return ConversationHandler.END

    if amount is None:
        await update.message.reply_text(
            "Использование: /debt <сумма> [валюта] [@username]\n"
            "Примеры: /debt 150\n"
            "         /debt 100 VND @alice"
        )
        return ConversationHandler.END

    if amount <= 0:
        await update.message.reply_text("Сумма должна быть положительной.")
        return ConversationHandler.END

    # --- Resolve creditor ---
    creditor_id: int | None = None

    if username:
        member = await db.get_user_by_username(username, chat_id)
        if not member:
            await update.message.reply_text(
                f"Пользователь @{username} не найден в этом чате. "
                "Он должен написать хотя бы одно сообщение, чтобы бот его увидел."
            )
            return ConversationHandler.END
        creditor_id = member["user_id"]
        if creditor_id == user.id:
            await update.message.reply_text("Нельзя быть должным самому себе.")
            return ConversationHandler.END
    else:
        members = await db.get_chat_members(chat_id)
        others = [m for m in members if m["user_id"] != user.id]
        if len(others) == 1:
            creditor_id = others[0]["user_id"]
        elif len(others) == 0:
            await update.message.reply_text(
                "Других участников пока не найдено. "
                "Они должны написать хотя бы одно сообщение."
            )
            return ConversationHandler.END
        # else creditor_id stays None → will show selection keyboard

    # --- Resolve currency ---
    currency: str | None = None
    suggested: str | None = None

    if not currency_str:
        currency = "USD"
    elif is_valid_currency(currency_str):
        currency = normalize_currency(currency_str)
    else:
        suggested = suggest_currency(currency_str)
        if not suggested:
            await update.message.reply_text(
                f'Неизвестная валюта "{currency_str}". '
                "Используй код ISO 4217 (например USD, EUR, VND, JPY)."
            )
            return ConversationHandler.END
        # Will ask for confirmation below

    # --- Store pending state ---
    state = PendingDebtState(
        amount=amount,
        raw_currency=currency_str or "USD",
        currency=currency,
        suggested_currency=suggested,
        creditor_id=creditor_id,
        chat_id=chat_id,
    )
    context.user_data["pending_debt"] = state

    # --- Ask for currency confirmation first (if needed) ---
    if currency is None:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Yes ✓", callback_data=f"currency_yes:{suggested}"),
            InlineKeyboardButton("No ✗", callback_data="currency_no"),
        ]])
        await update.message.reply_text(
            f'Вы имели в виду <b>{suggested}</b>?',
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        return AWAIT_CURRENCY_CONFIRM

    # --- Ask for recipient if still unknown ---
    if creditor_id is None:
        keyboard = await build_member_keyboard(db, chat_id, user.id, prefix="recipient")
        if not keyboard:
            await update.message.reply_text(
                "Других участников пока не найдено. "
                "Они должны написать хотя бы одно сообщение."
            )
            return ConversationHandler.END
        await update.message.reply_text("Кому ты должен?", reply_markup=keyboard)
        return AWAIT_RECIPIENT_SELECT

    # --- All resolved: save immediately ---
    await _save_and_reply(db, state, user.id, context, update, edit=False)
    return ConversationHandler.END


async def handle_currency_confirm(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    db: Database = context.bot_data["db"]
    state: PendingDebtState | None = context.user_data.get("pending_debt")

    if not state:
        await query.edit_message_text(
            "Время вышло. Введи /debt заново."
        )
        return ConversationHandler.END

    if query.data == "currency_no":
        await query.edit_message_text(
            "Отменено. Введи /debt с правильным кодом валюты."
        )
        context.user_data.pop("pending_debt", None)
        return ConversationHandler.END

    # currency_yes:<CODE>
    code = query.data.split(":", 1)[1]
    state.currency = code

    # If recipient is still unknown, ask now
    if state.creditor_id is None:
        keyboard = await build_member_keyboard(
            db, state.chat_id, query.from_user.id, prefix="recipient"
        )
        if not keyboard:
            await query.edit_message_text(
                "Других участников пока не найдено."
            )
            context.user_data.pop("pending_debt", None)
            return ConversationHandler.END
        await query.edit_message_text("Кому ты должен?", reply_markup=keyboard)
        return AWAIT_RECIPIENT_SELECT

    await _save_and_reply(db, state, query.from_user.id, context, query, edit=True)
    return ConversationHandler.END


async def handle_recipient_select(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    db: Database = context.bot_data["db"]
    state: PendingDebtState | None = context.user_data.get("pending_debt")

    if not state:
        await query.edit_message_text(
            "Время вышло. Введи /debt заново."
        )
        return ConversationHandler.END

    creditor_id = int(query.data.split(":", 1)[1])
    if creditor_id == query.from_user.id:
        await query.edit_message_text("Нельзя быть должным самому себе. Введи /debt заново.")
        context.user_data.pop("pending_debt", None)
        return ConversationHandler.END

    state.creditor_id = creditor_id
    await _save_and_reply(db, state, query.from_user.id, context, query, edit=True)
    return ConversationHandler.END


def build_debt_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("debt", debt_command)],
        states={
            AWAIT_CURRENCY_CONFIRM: [
                CallbackQueryHandler(
                    handle_currency_confirm,
                    pattern=r"^currency_(yes:.+|no)$",
                )
            ],
            AWAIT_RECIPIENT_SELECT: [
                CallbackQueryHandler(
                    handle_recipient_select,
                    pattern=r"^recipient:\d+$",
                )
            ],
        },
        fallbacks=[CommandHandler("debt", debt_command)],
        conversation_timeout=120,
        name="debt_conversation",
    )
