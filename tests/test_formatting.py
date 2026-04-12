from bot.formatting import display_name, format_debt_summary, format_settled_summary


def _user(user_id: int, username: str | None = None, full_name: str = "User") -> dict:
    return {"user_id": user_id, "username": username, "full_name": full_name}


def test_display_name_with_username():
    assert display_name(_user(1, "alice")) == "@alice"


def test_display_name_without_username():
    assert display_name(_user(1, None, "Alice Smith")) == "Alice Smith"


def test_format_empty():
    assert format_debt_summary([], {}) == "No active debts."


def test_format_single_debt():
    debts = [{"debtor_id": 1, "creditor_id": 2, "currency": "USD", "total": 150}]
    lookup = {1: _user(1, "alice"), 2: _user(2, "bob")}
    result = format_debt_summary(debts, lookup)
    assert result == "@alice → @bob: 150 USD"


def test_format_multiple_currencies_same_pair():
    debts = [
        {"debtor_id": 1, "creditor_id": 2, "currency": "USD", "total": 150},
        {"debtor_id": 1, "creditor_id": 2, "currency": "VND", "total": 100000},
    ]
    lookup = {1: _user(1, "alice"), 2: _user(2, "bob")}
    result = format_debt_summary(debts, lookup)
    assert "USD" in result
    assert "VND" in result
    assert "@alice → @bob" in result


def test_format_multiple_pairs():
    debts = [
        {"debtor_id": 1, "creditor_id": 2, "currency": "USD", "total": 50},
        {"debtor_id": 3, "creditor_id": 1, "currency": "EUR", "total": 20},
    ]
    lookup = {
        1: _user(1, "alice"),
        2: _user(2, "bob"),
        3: _user(3, "carol"),
    }
    result = format_debt_summary(debts, lookup)
    assert "@alice → @bob: 50 USD" in result
    assert "@carol → @alice: 20 EUR" in result


def test_format_settled_summary():
    result = format_settled_summary({"USD": 150.0})
    assert "150 USD" in result
    assert "Settled" in result


def test_format_settled_multiple_currencies():
    result = format_settled_summary({"USD": 50.0, "VND": 100000.0})
    assert "USD" in result
    assert "VND" in result
