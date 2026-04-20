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
from bot.formatting import display_name, format_debt_summary
from bot.handlers.common import build_member_keyboard, parse_amount_currency_username
from bot.models import DebtRecord, PendingDebtState

# ConversationHandler states
AWAIT_CURRENCY_CONFIRM = 0
AWAIT_RECIPIENT_SELECT = 1
AWAIT_CHAT_SELECT = 2


async def _apply_debt_with_netting(
    db: Database,
    chat_id: int,
    debtor_id: int,
    creditor_id: int,
    amount: float,   # positive = new debt, negative = payment
    currency: str,
) -> None:
    """
    Apply a debt entry with automatic netting.

    Positive amount: debtor owes creditor more.
      - First cancels any reverse debt (creditor → debtor).
      - Adds remainder as a new forward debt if any.

    Negative amount: debtor is paying creditor.
      - Reduces forward debt (debtor → creditor).
      - If overpayment, creates reverse debt (creditor → debtor) for the excess.
    """
    if amount > 0:
        reverse = await db.get_debt_total(chat_id, creditor_id, debtor_id, currency)
        if reverse > 0:
            if amount <= reverse:
                await db.settle_debt(chat_id, creditor_id, debtor_id, currency, amount)
                return
            # Wipe reverse debt and add net forward debt
            await db.settle_debt(chat_id, creditor_id, debtor_id, currency, None)
            amount = round(amount - reverse, 2)
        await db.add_debt(
            DebtRecord(
                debtor_id=debtor_id,
                creditor_id=creditor_id,
                amount=amount,
                currency=currency,
                chat_id=chat_id,
            )
        )
    else:
        # Negative = payment from debtor to creditor
        payment = round(abs(amount), 2)
        forward = await db.get_debt_total(chat_id, debtor_id, creditor_id, currency)
        if forward > 0:
            if payment <= forward:
                await db.settle_debt(chat_id, debtor_id, creditor_id, currency, payment)
                return
            # Overpayment: wipe forward debt, create reverse for the excess
            await db.settle_debt(chat_id, debtor_id, creditor_id, currency, None)
            excess = round(payment - forward, 2)
            await db.add_debt(
                DebtRecord(
                    debtor_id=creditor_id,
                    creditor_id=debtor_id,
                    amount=excess,
                    currency=currency,
                    chat_id=chat_id,
                )
            )
        else:
            # No existing debt — creditor now owes debtor
            await db.add_debt(
                DebtRecord(
                    debtor_id=creditor_id,
                    creditor_id=debtor_id,
                    amount=payment,
                    currency=currency,
                    chat_id=chat_id,
                )
            )


async def _save_and_reply(
    db: Database,
    state: PendingDebtState,
    from_user_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    reply_target,
    edit: bool = False,
) -> None:
    await _apply_debt_with_netting(
        db,
        chat_id=state.chat_id,
        debtor_id=from_user_id,
        creditor_id=state.creditor_id,
        amount=state.amount,
        currency=state.currency,
    )
    active_debts = await db.get_active_debts(state.chat_id)
    members = await db.get_chat_members(state.chat_id)
    user_lookup = {m["user_id"]: m for m in members}

    debtor = user_lookup.get(from_user_id, {"user_id": from_user_id, "full_name": str(from_user_id)})
    creditor = user_lookup.get(state.creditor_id, {"user_id": state.creditor_id, "full_name": str(state.creditor_id)})
    abs_amount = abs(state.amount)

    action = f"💸 {abs_amount:g} {state.currency}  {display_name(debtor)} → {display_name(creditor)}"
    summary = format_debt_summary(active_debts, user_lookup)
    text = f"{action}\n\n{summary}"

    if edit:
        await reply_target.edit_message_text(text)
    else:
        await reply_target.message.reply_text(text)

    context.user_data.pop("pending_debt", None)


async def _save_and_reply_multi(
    db: Database,
    state: PendingDebtState,
    from_user_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    reply_target,
    edit: bool = False,
) -> None:
    """Handle split debt across multiple creditors."""
    n = len(state.creditor_ids)
    per_amount = round(abs(state.amount) / n, 2)
    signed = per_amount if state.amount > 0 else -per_amount

    for creditor_id in state.creditor_ids:
        await _apply_debt_with_netting(
            db,
            chat_id=state.chat_id,
            debtor_id=from_user_id,
            creditor_id=creditor_id,
            amount=signed,
            currency=state.currency,
        )

    active_debts = await db.get_active_debts(state.chat_id)
    members = await db.get_chat_members(state.chat_id)
    user_lookup = {m["user_id"]: m for m in members}
    debtor = user_lookup.get(from_user_id, {"user_id": from_user_id, "full_name": str(from_user_id)})

    header = f"💸 {abs(state.amount):g} {state.currency} ÷ {n} = {per_amount:g} {state.currency}"
    lines = [header]
    for creditor_id in state.creditor_ids:
        creditor = user_lookup.get(creditor_id, {"user_id": creditor_id, "full_name": str(creditor_id)})
        lines.append(f"  {display_name(debtor)} → {display_name(creditor)}")

    summary = format_debt_summary(active_debts, user_lookup)
    text = "\n".join(lines) + "\n\n" + summary

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
    is_private = update.effective_chat.type == "private"

    # --- Parse arguments ---
    try:
        amount, currency_str, usernames = parse_amount_currency_username(
            context.args or []
        )
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return ConversationHandler.END

    if amount is None:
        await update.message.reply_text(
            "Использование: /debt <сумма> [валюта] [@username ...]\n"
            "Примеры:\n"
            "  /debt 150              — ты должен 150 USD\n"
            "  /debt -150             — ты отдал 150 USD\n"
            "  /debt 300 руб @a @b @c — поровну на троих"
        )
        return ConversationHandler.END

    if amount == 0:
        await update.message.reply_text("Сумма не может быть равна нулю.")
        return ConversationHandler.END

    if is_private and not usernames:
        await update.message.reply_text(
            "В личке укажи получателя через @username, например:\n"
            "  /debt -10 USD @alice"
        )
        return ConversationHandler.END

    if is_private and len(usernames) > 1:
        await update.message.reply_text(
            "Разделение долга между несколькими пользователями работает только в групповых чатах."
        )
        return ConversationHandler.END

    # --- Resolve currency ---
    currency: str | None = None
    suggested: str | None = None

    if not currency_str:
        if is_private:
            currency = await db.get_user_default_currency(user.id)
        else:
            currency = await db.get_chat_default_currency(chat_id)
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

    # --- Multi-creditor split (group only) ---
    if len(usernames) > 1:
        creditor_ids: list[int] = []
        for uname in usernames:
            member = await db.get_user_by_username(uname, chat_id)
            if not member:
                await update.message.reply_text(
                    f"Пользователь @{uname} пока не виден боту.\n\n"
                    f"Попроси @{uname} написать любое сообщение в группе — "
                    "после этого команда заработает."
                )
                return ConversationHandler.END
            if member["user_id"] == user.id:
                await update.message.reply_text("Нельзя быть должным самому себе.")
                return ConversationHandler.END
            creditor_ids.append(member["user_id"])

        state = PendingDebtState(
            amount=amount,
            raw_currency=currency_str or "USD",
            currency=currency,
            suggested_currency=suggested,
            creditor_ids=creditor_ids,
            chat_id=chat_id,
        )
        context.user_data["pending_debt"] = state

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

        await _save_and_reply_multi(db, state, user.id, context, update, edit=False)
        return ConversationHandler.END

    # --- Single creditor ---
    username = usernames[0] if usernames else None
    creditor_id: int | None = None
    target_chat_id: int = chat_id  # group: current chat; private: resolved below

    if is_private:
        # Look up user globally; determine chat from common memberships
        member = await db.get_user_by_username_global(username)
        if not member:
            await update.message.reply_text(
                f"Бот не знает пользователя @{username}. "
                "Он должен написать любое сообщение в группе где есть бот."
            )
            return ConversationHandler.END
        creditor_id = member["user_id"]
        if creditor_id == user.id:
            await update.message.reply_text("Нельзя быть должным самому себе.")
            return ConversationHandler.END

        common = await db.get_common_chats(user.id, creditor_id)
        if not common:
            await update.message.reply_text(
                f"У тебя с @{username} нет общих групп с ботом."
            )
            return ConversationHandler.END
        if len(common) == 1:
            target_chat_id = int(common[0]["chat_id"])
        else:
            state = PendingDebtState(
                amount=amount,
                raw_currency=currency_str or "USD",
                currency=currency,
                suggested_currency=suggested,
                creditor_id=creditor_id,
                chat_id=0,  # will be set after chat selection
            )
            context.user_data["pending_debt"] = state
            buttons = [
                [InlineKeyboardButton(
                    c.get("chat_title") or f"Чат {c['chat_id']}",
                    callback_data=f"debt_chat:{c['chat_id']}",
                )]
                for c in common
            ]
            await update.message.reply_text(
                f"В каком чате записать долг с @{username}?",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            return AWAIT_CHAT_SELECT
    elif username:
        member = await db.get_user_by_username(username, chat_id)
        if not member:
            await update.message.reply_text(
                f"Пользователь @{username} пока не виден боту.\n\n"
                f"Попроси @{username} написать любое сообщение в группе — "
                "после этого команда заработает."
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

    chat_id = target_chat_id

    state = PendingDebtState(
        amount=amount,
        raw_currency=currency_str or "USD",
        currency=currency,
        suggested_currency=suggested,
        creditor_id=creditor_id,
        chat_id=chat_id,
    )
    context.user_data["pending_debt"] = state

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

    # Multi-creditor split — all recipients already known
    if state.creditor_ids:
        await _save_and_reply_multi(db, state, query.from_user.id, context, query, edit=True)
        return ConversationHandler.END

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


async def handle_chat_select(
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

    state.chat_id = int(query.data.split(":", 1)[1])

    if state.currency is None:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Yes ✓", callback_data=f"currency_yes:{state.suggested_currency}"),
            InlineKeyboardButton("No ✗", callback_data="currency_no"),
        ]])
        await query.edit_message_text(
            f'Вы имели в виду <b>{state.suggested_currency}</b>?',
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        return AWAIT_CURRENCY_CONFIRM

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
            AWAIT_CHAT_SELECT: [
                CallbackQueryHandler(
                    handle_chat_select,
                    pattern=r"^debt_chat:-?\d+$",
                )
            ],
        },
        fallbacks=[CommandHandler("debt", debt_command)],
        conversation_timeout=120,
        name="debt_conversation",
    )
