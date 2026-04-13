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

# Russian aliases → ISO 4217
RU_ALIASES: dict[str, str] = {
    # Рубль
    "руб": "RUB", "рубль": "RUB", "рублей": "RUB", "рубля": "RUB", "рублю": "RUB",
    # Доллар
    "дол": "USD", "долл": "USD", "доллар": "USD", "долларов": "USD", "доллара": "USD",
    # Евро
    "евро": "EUR", "евр": "EUR",
    # Юань
    "юань": "CNY", "юаня": "CNY", "юаней": "CNY",
    # Тенге
    "тенге": "KZT",
    # Гривна
    "гривна": "UAH", "гривен": "UAH", "гривны": "UAH",
    # Иена
    "иена": "JPY", "иен": "JPY", "йена": "JPY",
    # Фунт
    "фунт": "GBP", "фунтов": "GBP", "фунта": "GBP",
    # Франк
    "франк": "CHF", "франков": "CHF",
    # Донг
    "донг": "VND", "донгов": "VND",
    # Лира
    "лира": "TRY", "лиры": "TRY", "лир": "TRY",
}

# Sorted list for rapidfuzz (frozenset is unordered)
_CURRENCIES_LIST: list[str] = sorted(CURRENCIES)


def is_valid_currency(code: str) -> bool:
    """Return True if code is a known ISO 4217 code or Russian alias."""
    return code.lower() in RU_ALIASES or code.upper() in CURRENCIES


def normalize_currency(code: str) -> str:
    """Return uppercase ISO 4217 code. Raises ValueError if unknown."""
    alias = RU_ALIASES.get(code.lower())
    if alias:
        return alias
    upper = code.upper()
    if upper not in CURRENCIES:
        raise ValueError(f"Unknown currency code: {code!r}")
    return upper


def suggest_currency(code: str, cutoff: int = 70) -> str | None:
    """
    Fuzzy-match code against the ISO 4217 list.
    Returns the best match if score >= cutoff, else None.
    """
    alias = RU_ALIASES.get(code.lower())
    if alias:
        return alias
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
