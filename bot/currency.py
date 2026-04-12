from rapidfuzz import fuzz, process

# Full ISO 4217 active currency codes
CURRENCIES: frozenset[str] = frozenset({
    "AED", "AFN", "ALL", "AMD", "ANG", "AOA", "ARS", "AUD", "AWG", "AZN",
    "BAM", "BBD", "BDT", "BGN", "BHD", "BIF", "BMD", "BND", "BOB", "BOV",
    "BRL", "BSD", "BTN", "BWP", "BYN", "BZD", "CAD", "CDF", "CHE", "CHF",
    "CHW", "CLF", "CLP", "CNY", "COP", "COU", "CRC", "CUP", "CVE", "CZK",
    "DJF", "DKK", "DOP", "DZD", "EGP", "ERN", "ETB", "EUR", "FJD", "FKP",
    "GBP", "GEL", "GHS", "GIP", "GMD", "GNF", "GTQ", "GYD", "HKD", "HNL",
    "HTG", "HUF", "IDR", "ILS", "INR", "IQD", "IRR", "ISK", "JMD", "JOD",
    "JPY", "KES", "KGS", "KHR", "KMF", "KPW", "KRW", "KWD", "KYD", "KZT",
    "LAK", "LBP", "LKR", "LRD", "LSL", "LYD", "MAD", "MDL", "MGA", "MKD",
    "MMK", "MNT", "MOP", "MRU", "MUR", "MVR", "MWK", "MXN", "MXV", "MYR",
    "MZN", "NAD", "NGN", "NIO", "NOK", "NPR", "NZD", "OMR", "PAB", "PEN",
    "PGK", "PHP", "PKR", "PLN", "PYG", "QAR", "RON", "RSD", "RUB", "RWF",
    "SAR", "SBD", "SCR", "SDG", "SEK", "SGD", "SHP", "SLE", "SLL", "SOS",
    "SRD", "SSP", "STN", "SVC", "SYP", "SZL", "THB", "TJS", "TMT", "TND",
    "TOP", "TRY", "TTD", "TWD", "TZS", "UAH", "UGX", "USD", "USN", "UYI",
    "UYU", "UYW", "UZS", "VED", "VES", "VND", "VUV", "WST", "XAF", "XAG",
    "XAU", "XBA", "XBB", "XBC", "XBD", "XCD", "XDR", "XOF", "XPD", "XPF",
    "XPT", "XSU", "XTS", "XUA", "XXX", "YER", "ZAR", "ZMW", "ZWG",
})

# Sorted list for rapidfuzz (frozenset is unordered)
_CURRENCIES_LIST: list[str] = sorted(CURRENCIES)


def is_valid_currency(code: str) -> bool:
    """Return True if code is a known ISO 4217 currency code (case-insensitive)."""
    return code.upper() in CURRENCIES


def normalize_currency(code: str) -> str:
    """Return uppercase ISO 4217 code. Raises ValueError if unknown."""
    upper = code.upper()
    if upper not in CURRENCIES:
        raise ValueError(f"Unknown currency code: {code!r}")
    return upper


def suggest_currency(code: str, cutoff: int = 70) -> str | None:
    """
    Fuzzy-match code against the ISO 4217 list.
    Returns the best match if score >= cutoff, else None.
    """
    upper = code.upper()
    if upper in CURRENCIES:
        return upper
    result = process.extractOne(
        upper,
        _CURRENCIES_LIST,
        scorer=fuzz.WRatio,
        score_cutoff=cutoff,
    )
    return result[0] if result else None
