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
from bot.formatting import format_debt_summary, format_settled_summary
from bot.handlers.common import build_member_keyboard, parse_amount_currency_username
from bot.models import PendingSettleState

# ConversationHandler states
AWAIT_SETTLE_CURRENCY_CONFIRM = 0
AWAIT_SETTLE_RECIPIENT_SELECT = 1


async def _do_settle_and_reply(
    db: Database,
    state: PendingSettleState,
    from_user_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    reply_target,
    edit: bool = False,
) -> None:
    try:
        if state.currency:
            settled = {
                state.currency: await db.settle_debt(
                    state.chat_id,
                    from_user_id,
                    state.creditor_id,
                    state.currency,
                    state.settle_amount,
                )
            }
        else:
            settled = await db.settle_all_debts(
                state.chat_id, from_user_id, state.creditor_id
            )
    except ValueError as exc:
        text = f"{exc}"
        if edit:
            await reply_target.edit_message_text(text)
        else:
            await reply_target.message.reply_text(text)
        context.user_data.pop("pending_settle", None)
        return

    active_debts = await db.get_active_debts(state.chat_id)
    members = await db.get_chat_members(state.chat_id)
    user_lookup = {m["user_id"]: m for m in members}
    summary = format_debt_summary(active_debts, user_lookup)
    text = f"{format_settled_summary(settled)}\n\n{summary}"

    if edit:
        await reply_target.edit_message_text(text)
    else:
        await reply_target.message.reply_text(text)

    context.user_data.pop("pending_settle", None)


async def settle_command(
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

    # --- Resolve creditor ---
    creditor_id: int | None = None

    if username:
        member = await db.get_user_by_username(username, chat_id)
        if not member:
            await update.message.reply_text(
                f"User @{username} not found in this chat."
            )
            return ConversationHandler.END
        creditor_id = member["user_id"]
    else:
        members = await db.get_chat_members(chat_id)
        others = [m for m in members if m["user_id"] != user.id]
        if len(others) == 1:
            creditor_id = others[0]["user_id"]
        elif len(others) == 0:
            await update.message.reply_text("No other members found in this chat.")
            return ConversationHandler.END
        # else: will ask

    # --- Resolve currency ---
    currency: str | None = None
    suggested: str | None = None

    if currency_str:
        if is_valid_currency(currency_str):
            currency = normalize_currency(currency_str)
        else:
            suggested = suggest_currency(currency_str)
            if not suggested:
                await update.message.reply_text(
                    f'Unknown currency "{currency_str}". '
                    "Use a valid ISO 4217 code (e.g. USD, EUR, VND)."
                )
                return ConversationHandler.END
    # currency=None means "settle all currencies"

    # --- Store pending state ---
    state = PendingSettleState(
        settle_amount=amount,
        raw_currency=currency_str,
        currency=currency,
        suggested_currency=suggested,
        creditor_id=creditor_id,
        chat_id=chat_id,
    )
    context.user_data["pending_settle"] = state

    # --- Ask for currency confirmation if needed ---
    if currency_str and currency is None:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "Yes ✓", callback_data=f"settle_currency_yes:{suggested}"
            ),
            InlineKeyboardButton("No ✗", callback_data="settle_currency_no"),
        ]])
        await update.message.reply_text(
            f'Did you mean *{suggested}*?',
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
        return AWAIT_SETTLE_CURRENCY_CONFIRM

    # --- Ask for recipient if needed ---
    if creditor_id is None:
        keyboard = await build_member_keyboard(
            db, chat_id, user.id, prefix="settle_recipient"
        )
        if not keyboard:
            await update.message.reply_text("No other members found in this chat.")
            return ConversationHandler.END
        await update.message.reply_text(
            "Settle debt with whom?", reply_markup=keyboard
        )
        return AWAIT_SETTLE_RECIPIENT_SELECT

    # --- All resolved: settle immediately ---
    await _do_settle_and_reply(db, state, user.id, context, update, edit=False)
    return ConversationHandler.END


async def handle_settle_currency_confirm(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    db: Database = context.bot_data["db"]
    state: PendingSettleState | None = context.user_data.get("pending_settle")

    if not state:
        await query.edit_message_text(
            "This selection has expired. Please re-enter /settle."
        )
        return ConversationHandler.END

    if query.data == "settle_currency_no":
        await query.edit_message_text(
            "Cancelled. Please re-enter /settle with the correct currency code."
        )
        context.user_data.pop("pending_settle", None)
        return ConversationHandler.END

    code = query.data.split(":", 1)[1]
    state.currency = code

    if state.creditor_id is None:
        keyboard = await build_member_keyboard(
            db, state.chat_id, query.from_user.id, prefix="settle_recipient"
        )
        if not keyboard:
            await query.edit_message_text("No other members found in this chat.")
            context.user_data.pop("pending_settle", None)
            return ConversationHandler.END
        await query.edit_message_text(
            "Settle debt with whom?", reply_markup=keyboard
        )
        return AWAIT_SETTLE_RECIPIENT_SELECT

    await _do_settle_and_reply(
        db, state, query.from_user.id, context, query, edit=True
    )
    return ConversationHandler.END


async def handle_settle_recipient_select(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    db: Database = context.bot_data["db"]
    state: PendingSettleState | None = context.user_data.get("pending_settle")

    if not state:
        await query.edit_message_text(
            "This selection has expired. Please re-enter /settle."
        )
        return ConversationHandler.END

    creditor_id = int(query.data.split(":", 1)[1])
    state.creditor_id = creditor_id

    await _do_settle_and_reply(
        db, state, query.from_user.id, context, query, edit=True
    )
    return ConversationHandler.END


def build_settle_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("settle", settle_command)],
        states={
            AWAIT_SETTLE_CURRENCY_CONFIRM: [
                CallbackQueryHandler(
                    handle_settle_currency_confirm,
                    pattern=r"^settle_currency_(yes:.+|no)$",
                )
            ],
            AWAIT_SETTLE_RECIPIENT_SELECT: [
                CallbackQueryHandler(
                    handle_settle_recipient_select,
                    pattern=r"^settle_recipient:\d+$",
                )
            ],
        },
        fallbacks=[CommandHandler("settle", settle_command)],
        conversation_timeout=120,
        name="settle_conversation",
    )
