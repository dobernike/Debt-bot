from collections import defaultdict


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


def format_settled_summary(settled: dict[str, float]) -> str:
    parts = " + ".join(f"{v:g} {k}" for k, v in sorted(settled.items()))
    return f"✅ Погашено: {parts}"


def format_help() -> str:
    return (
        "<b>Debt Bot</b> — учёт долгов в групповых чатах\n\n"
        "<b>Записать долг:</b>\n"
        "<code>/debt 150</code> — ты должен другому участнику 150 USD\n"
        "<code>/debt 100 VND</code> — ты должен 100 вьетнамских донгов\n"
        "<code>/debt 50 @username</code> — ты должен @username 50 USD\n"
        "<code>/debt 50 EUR @username</code> — ты должен @username 50 EUR\n"
        "<code>/debt @username 100+200</code> — сумма как выражение (= 300)\n"
        "<code>/debt -150</code> — ты заплатил 150 (отрицательный долг)\n\n"
        "<b>Погасить долг:</b>\n"
        "<code>/settle</code> — погасить весь долг (чат с двумя участниками)\n"
        "<code>/settle @username</code> — погасить всё что должен @username\n"
        "<code>/settle 50 USD @username</code> — частичное погашение\n\n"
        "<b>Посмотреть долги:</b>\n"
        "<code>/debts</code> — текущий список долгов\n\n"
        "<i>Валюта по умолчанию — USD.</i>"
    )
