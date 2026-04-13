from __future__ import annotations

import asyncpg

from bot.models import DebtRecord


class Database:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def init(self) -> None:
        # ssl="require" is needed for hosted providers like Neon or Supabase;
        # asyncpg ignores it for local connections.
        self._pool = await asyncpg.create_pool(self._dsn, ssl="require")
        await self._create_tables()

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    async def _create_tables(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id   BIGINT PRIMARY KEY,
                    username  TEXT,
                    full_name TEXT NOT NULL
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    chat_id    BIGINT PRIMARY KEY,
                    chat_title TEXT
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_members (
                    chat_id BIGINT NOT NULL REFERENCES chats(chat_id),
                    user_id BIGINT NOT NULL REFERENCES users(user_id),
                    PRIMARY KEY (chat_id, user_id)
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS debts (
                    id             SERIAL PRIMARY KEY,
                    chat_id        BIGINT NOT NULL REFERENCES chats(chat_id),
                    debtor_id      BIGINT NOT NULL REFERENCES users(user_id),
                    creditor_id    BIGINT NOT NULL REFERENCES users(user_id),
                    amount         NUMERIC(15, 2) NOT NULL CHECK(amount > 0),
                    currency       TEXT NOT NULL DEFAULT 'USD',
                    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    settled_at     TIMESTAMPTZ,
                    settled_amount NUMERIC(15, 2)
                )
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_debts_chat ON debts(chat_id)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_debts_parties ON debts(debtor_id, creditor_id)"
            )

    async def upsert_user(
        self, user_id: int, username: str | None, full_name: str
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO users (user_id, username, full_name)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id) DO UPDATE
                    SET username  = EXCLUDED.username,
                        full_name = EXCLUDED.full_name
                """,
                user_id,
                username,
                full_name,
            )

    async def upsert_chat(self, chat_id: int, chat_title: str | None) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO chats (chat_id, chat_title)
                VALUES ($1, $2)
                ON CONFLICT (chat_id) DO UPDATE
                    SET chat_title = EXCLUDED.chat_title
                """,
                chat_id,
                chat_title,
            )

    async def upsert_chat_member(self, chat_id: int, user_id: int) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO chat_members (chat_id, user_id)
                VALUES ($1, $2)
                ON CONFLICT DO NOTHING
                """,
                chat_id,
                user_id,
            )

    async def add_debt(self, record: DebtRecord) -> int:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO debts (chat_id, debtor_id, creditor_id, amount, currency)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                record.chat_id,
                record.debtor_id,
                record.creditor_id,
                record.amount,
                record.currency,
            )
            return row["id"]

    async def get_chat_members(self, chat_id: int) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT u.user_id, u.username, u.full_name
                FROM chat_members cm
                JOIN users u ON cm.user_id = u.user_id
                WHERE cm.chat_id = $1
                """,
                chat_id,
            )
            return [dict(r) for r in rows]

    async def get_active_debts(self, chat_id: int) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT debtor_id, creditor_id, currency,
                       SUM(amount) AS total
                FROM debts
                WHERE chat_id = $1 AND settled_at IS NULL
                GROUP BY debtor_id, creditor_id, currency
                HAVING SUM(amount) > 0
                ORDER BY debtor_id, creditor_id, currency
                """,
                chat_id,
            )
            return [dict(r) for r in rows]

    async def get_all_debts_for_user(self, user_id: int) -> list[dict]:
        """
        Return all active debts where the user is debtor or creditor,
        across all chats. Each row includes chat_id and chat_title.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT d.chat_id,
                       c.chat_title,
                       d.debtor_id,
                       d.creditor_id,
                       d.currency,
                       SUM(d.amount) AS total
                FROM debts d
                JOIN chats c ON d.chat_id = c.chat_id
                WHERE d.settled_at IS NULL
                  AND (d.debtor_id = $1 OR d.creditor_id = $1)
                GROUP BY d.chat_id, c.chat_title, d.debtor_id, d.creditor_id, d.currency
                HAVING SUM(d.amount) > 0
                ORDER BY c.chat_title, d.debtor_id, d.creditor_id, d.currency
                """,
                user_id,
            )
            return [dict(r) for r in rows]

    async def get_transaction_history(self, chat_id: int, limit: int = 10) -> list[dict]:
        """Return the last `limit` debt entries for a chat, newest first."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT debtor_id, creditor_id, amount, currency, created_at
                FROM debts
                WHERE chat_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                chat_id,
                limit,
            )
            return [dict(r) for r in rows]

    async def get_transaction_history_for_user(self, user_id: int, limit: int = 10) -> list[dict]:
        """Return the last `limit` debt entries across all chats for a user, newest first."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT d.debtor_id, d.creditor_id, d.amount, d.currency, d.created_at,
                       d.chat_id, c.chat_title
                FROM debts d
                JOIN chats c ON d.chat_id = c.chat_id
                WHERE d.debtor_id = $1 OR d.creditor_id = $1
                ORDER BY d.created_at DESC
                LIMIT $2
                """,
                user_id,
                limit,
            )
            return [dict(r) for r in rows]

    async def get_users_by_ids(self, user_ids: list[int]) -> list[dict]:
        """Fetch user records for a list of user_ids."""
        if not user_ids:
            return []
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_id, username, full_name FROM users WHERE user_id = ANY($1)",
                user_ids,
            )
            return [dict(r) for r in rows]

    async def get_debt_total(
        self,
        chat_id: int,
        debtor_id: int,
        creditor_id: int,
        currency: str,
    ) -> float:
        """Return the total active debt for a specific (debtor, creditor, currency) triple."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COALESCE(SUM(amount), 0) AS total
                FROM debts
                WHERE chat_id = $1
                  AND debtor_id = $2
                  AND creditor_id = $3
                  AND currency = $4
                  AND settled_at IS NULL
                """,
                chat_id,
                debtor_id,
                creditor_id,
                currency,
            )
            return float(row["total"])

    async def get_user_by_username(
        self, username: str, chat_id: int
    ) -> dict | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT u.user_id, u.username, u.full_name
                FROM users u
                JOIN chat_members cm ON u.user_id = cm.user_id
                WHERE cm.chat_id = $1
                  AND LOWER(u.username) = LOWER($2)
                """,
                chat_id,
                username.lstrip("@"),
            )
            return dict(row) if row else None

    async def settle_debt(
        self,
        chat_id: int,
        debtor_id: int,
        creditor_id: int,
        currency: str,
        amount: float | None = None,
    ) -> float:
        """
        Settle debts for a specific currency pair.
        amount=None settles the full balance.
        Returns the amount settled.
        Raises ValueError if no debt or requested amount exceeds balance.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COALESCE(SUM(amount), 0) AS total
                FROM debts
                WHERE chat_id = $1
                  AND debtor_id = $2
                  AND creditor_id = $3
                  AND currency = $4
                  AND settled_at IS NULL
                """,
                chat_id,
                debtor_id,
                creditor_id,
                currency,
            )
            total = float(row["total"])
            if total == 0:
                raise ValueError(
                    f"No active {currency} debt found for this pair."
                )

            settle_amount = amount if amount is not None else total
            if settle_amount > total:
                raise ValueError(
                    f"Cannot settle {settle_amount} {currency}: "
                    f"only {total} {currency} is owed."
                )

            # Close all active rows for this pair + currency
            await conn.execute(
                """
                UPDATE debts
                SET settled_at = NOW(), settled_amount = amount
                WHERE chat_id = $1
                  AND debtor_id = $2
                  AND creditor_id = $3
                  AND currency = $4
                  AND settled_at IS NULL
                """,
                chat_id,
                debtor_id,
                creditor_id,
                currency,
            )

            # Re-insert remainder for partial settlement
            remainder = round(total - settle_amount, 2)
            if remainder > 0:
                await conn.execute(
                    """
                    INSERT INTO debts (chat_id, debtor_id, creditor_id, amount, currency)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    chat_id,
                    debtor_id,
                    creditor_id,
                    remainder,
                    currency,
                )

            return settle_amount

    async def settle_all_debts(
        self,
        chat_id: int,
        debtor_id: int,
        creditor_id: int,
    ) -> dict[str, float]:
        """
        Settle all currency debts for a pair.
        Returns {currency: amount_settled}.
        Raises ValueError if nothing to settle.
        """
        active = await self.get_active_debts(chat_id)
        pair_debts = [
            d
            for d in active
            if d["debtor_id"] == debtor_id and d["creditor_id"] == creditor_id
        ]
        if not pair_debts:
            raise ValueError("No active debts found for this pair.")

        settled: dict[str, float] = {}
        for debt in pair_debts:
            amount = await self.settle_debt(
                chat_id, debtor_id, creditor_id, debt["currency"], None
            )
            settled[debt["currency"]] = amount
        return settled
