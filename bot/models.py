from dataclasses import dataclass


@dataclass
class DebtRecord:
    debtor_id: int
    creditor_id: int
    amount: float
    currency: str
    chat_id: int


@dataclass
class PendingDebtState:
    """Stored in user_data during /debt ConversationHandler flow."""
    amount: float
    raw_currency: str = "USD"
    currency: str | None = None          # None until confirmed (fuzzy match)
    suggested_currency: str | None = None
    creditor_id: int | None = None       # None until selected (multi-user group)
    chat_id: int = 0
