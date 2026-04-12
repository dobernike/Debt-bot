import pytest

from bot.currency import is_valid_currency, normalize_currency, suggest_currency


def test_valid_currencies():
    assert is_valid_currency("USD") is True
    assert is_valid_currency("usd") is True
    assert is_valid_currency("EUR") is True
    assert is_valid_currency("VND") is True
    assert is_valid_currency("JPY") is True


def test_invalid_currencies():
    assert is_valid_currency("XXX") is True   # XXX is a valid ISO code (no currency)
    assert is_valid_currency("ZZZ") is False
    assert is_valid_currency("ABC") is False
    assert is_valid_currency("") is False


def test_normalize_currency():
    assert normalize_currency("usd") == "USD"
    assert normalize_currency("EUR") == "EUR"
    assert normalize_currency("vnd") == "VND"


def test_normalize_invalid_raises():
    with pytest.raises(ValueError):
        normalize_currency("ZZZ")


def test_suggest_close_match():
    # VNN is one character off from VND
    result = suggest_currency("VNN")
    assert result == "VND"


def test_suggest_case_insensitive():
    result = suggest_currency("usd")
    assert result == "USD"


def test_suggest_no_match():
    result = suggest_currency("ZZZZZ", cutoff=70)
    assert result is None


def test_suggest_exact_match():
    result = suggest_currency("EUR")
    assert result == "EUR"
