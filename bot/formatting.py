from collections import defaultdict
from datetime import timezone


def display_name(user: dict) -> str:
    """Return @username if available, otherwise full name."""
    if user.get("username"):
        return f"@{user['username']}"
    return user.get("full_name", str(user.get("user_id", "?")))


def format_debt_summary(
    debts: list[dict],
    user_lookup: dict[int, dict],
) -> str:
    if not debts:
        return "Долгов нет."

    # Group by (debtor_id, creditor_id) → {currency: total}
    grouped: dict[tuple[int, int], dict[str, float]] = defaultdict(dict)
    for row in debts:
        key = (int(row["debtor_id"]), int(row["creditor_id"]))
        grouped[key][row["currency"]] = float(row["total"])

    lines: list[str] = []
    for (debtor_id, creditor_id), balances in grouped.items():
        debtor = user_lookup.get(
            debtor_id, {"user_id": debtor_id, "full_name": str(debtor_id)}
        )
        creditor = user_lookup.get(
            creditor_id, {"user_id": creditor_id, "full_name": str(creditor_id)}
        )
        amounts_str = " + ".join(
            f"{v:g} {k}" for k, v in sorted(balances.items())
        )
        lines.append(
            f"{display_name(debtor)} → {display_name(creditor)}: {amounts_str}"
        )

    return "\n".join(lines)


def format_global_debt_summary(
    debts: list[dict],
    user_lookup: dict[int, dict],
) -> str:
    """
    For private chat: show all user's debts grouped by chat.

    Output example:
        📍 Путешествие в Азию
        @you → @alice: 150 USD

        📍 Общие расходы
        @bob → @you: 50 EUR
    """
    if not debts:
        return "Долгов нет."

    # Group rows by (chat_id, chat_title)
    by_chat: dict[tuple, list] = defaultdict(list)
    for row in debts:
        key = (row["chat_id"], row.get("chat_title") or f"Чат {row['chat_id']}")
        by_chat[key].append(row)

    sections: list[str] = []
    for (_, chat_title), chat_debts in by_chat.items():
        summary = format_debt_summary(chat_debts, user_lookup)
        sections.append(f"📍 <b>{chat_title}</b>\n{summary}")

    return "\n\n".join(sections)


def _format_history_rows(rows: list[dict], user_lookup: dict[int, dict]) -> str:
    """Render a list of transaction rows grouped by participant pair."""
    by_pair: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for row in rows:
        key = (
            min(int(row["debtor_id"]), int(row["creditor_id"])),
            max(int(row["debtor_id"]), int(row["creditor_id"])),
        )
        by_pair[key].append(row)

    sections: list[str] = []
    for (id_a, id_b), txs in by_pair.items():
        user_a = user_lookup.get(id_a, {"user_id": id_a, "full_name": str(id_a)})
        user_b = user_lookup.get(id_b, {"user_id": id_b, "full_name": str(id_b)})
        lines = [f"{display_name(user_a)} ↔ {display_name(user_b)}"]
        for tx in txs:
            debtor = user_lookup.get(int(tx["debtor_id"]), {"user_id": tx["debtor_id"], "full_name": str(tx["debtor_id"])})
            creditor = user_lookup.get(int(tx["creditor_id"]), {"user_id": tx["creditor_id"], "full_name": str(tx["creditor_id"])})
            dt = tx["created_at"].replace(tzinfo=timezone.utc) if tx["created_at"].tzinfo is None else tx["created_at"]
            date_str = dt.strftime("%-d %b, %H:%M")
            lines.append(
                f"  💸 {float(tx['amount']):g} {tx['currency']}  "
                f"{display_name(debtor)} → {display_name(creditor)}  {date_str}"
            )
        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def format_history(rows: list[dict], user_lookup: dict[int, dict]) -> str:
    """For group chat: transactions grouped by pair."""
    if not rows:
        return "История пуста."
    return _format_history_rows(rows, user_lookup)


def format_global_history(rows: list[dict], user_lookup: dict[int, dict]) -> str:
    """For private chat: transactions grouped by chat, then by pair."""
    if not rows:
        return "История пуста."

    by_chat: dict[tuple, list] = defaultdict(list)
    for row in rows:
        key = (row["chat_id"], row.get("chat_title") or f"Чат {row['chat_id']}")
        by_chat[key].append(row)

    sections: list[str] = []
    for (_, chat_title), chat_rows in by_chat.items():
        inner = _format_history_rows(chat_rows, user_lookup)
        sections.append(f"📍 <b>{chat_title}</b>\n{inner}")

    return "\n\n".join(sections)


def format_help() -> str:
    return (
        "<b>Debt Bot</b> — учёт долгов в групповых чатах\n\n"
        "<b>Записать долг:</b>\n"
        "<code>/debt 150</code> — ты должен другому участнику 150 USD\n"
        "<code>/debt 100 VND</code> — ты должен 100 вьетнамских донгов\n"
        "<code>/debt 50 @username</code> — ты должен @username 50 USD\n"
        "<code>/debt 50 EUR @username</code> — ты должен @username 50 EUR\n"
        "<code>/debt @username 100+200</code> — сумма как выражение (= 300)\n\n"
        "<b>Погасить долг (отрицательная сумма):</b>\n"
        "<code>/debt -150</code> — ты заплатил 150 другому участнику\n"
        "<code>/debt -50 @username</code> — ты заплатил 50 конкретному пользователю\n"
        "<code>/debt -50 EUR @username</code> — частичное погашение в EUR\n\n"
        "<i>Отрицательный долг автоматически зачитывается: если ты должен 100 и платишь 150 — "
        "теперь тебе должны 50.</i>\n\n"
        "<b>Посмотреть долги:</b>\n"
        "<code>/debts</code> — текущий список долгов\n\n"
        "<i>Валюта по умолчанию — USD.</i>"
    )
