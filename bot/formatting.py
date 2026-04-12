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
    """
    Render all active debts as a human-readable string.

    Groups multiple currencies for the same pair on one line:
        @alice → @bob: 150 USD + 100 VND

    Returns "No active debts." when the list is empty.
    """
    if not debts:
        return "No active debts."

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


def format_settled_summary(settled: dict[str, float]) -> str:
    """Format the result of a settle operation: 'Settled: 150 USD + 100 VND'"""
    parts = " + ".join(f"{v:g} {k}" for k, v in sorted(settled.items()))
    return f"✅ Settled: {parts}"


def format_help() -> str:
    return (
        "*Debt Bot* — track who owes whom\n\n"
        "*Record a debt:*\n"
        "`/debt 150` — you owe the other person 150 USD\n"
        "`/debt 100 VND` — you owe 100 Vietnamese Dong\n"
        "`/debt 50 @username` — you owe @username 50 USD\n"
        "`/debt 50 EUR @username` — you owe @username 50 EUR\n\n"
        "*Settle a debt:*\n"
        "`/settle` — settle all you owe \\(2\\-person chat\\)\n"
        "`/settle @username` — settle all you owe to @username\n"
        "`/settle 50 USD @username` — partial settlement\n\n"
        "*View debts:*\n"
        "`/debts` — show current debt summary\n\n"
        "_Default currency is USD\\._"
    )
