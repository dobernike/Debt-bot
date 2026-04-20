from dataclasses import dataclass, field


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
    creditor_id: int | None = None       # single creditor (keyboard selection)
    creditor_ids: list[int] = field(default_factory=list)  # multi-split
    chat_id: int = 0
