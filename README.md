# Debt-bot

A Telegram bot for tracking shared debts inside group chats.

## Features

- `/debt 150` — record that you owe the other person 150 USD
- `/debt 100 VND @alice` — owe @alice 100 Vietnamese Dong
- Typo detection: type `vnn` and the bot asks "Did you mean VND?"
- In groups with 3+ members the bot shows a picker so you can choose who you owe
- `/settle` / `/settle @alice` / `/settle 50 USD @alice` — full or partial settlement
- `/debts` — view current debt summary at any time
- Multi-currency per pair: `@alice → @bob: 150 USD + 100 VND`

## Usage examples

```
/debt 150
/debt 100 VND
/debt 50 EUR @alice
/settle
/settle @alice
/settle 50 USD @alice
/debts
/help
```

## Local setup

1. Clone the repo and create a virtual environment:
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Create a `.env` file (copy from `.env.example`):
   ```
   BOT_TOKEN=your_telegram_bot_token
   DATABASE_URL=postgresql://user:password@localhost:5432/debtbot
   ```

3. Create the database (PostgreSQL must be running):
   ```bash
   createdb debtbot
   ```

4. Run the bot:
   ```bash
   python -m bot.main
   ```

## Deploy on Railway

1. Push this repo to GitHub.
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**.
3. Inside the project, click **+ New** → **Database** → **PostgreSQL**.
   Railway auto-injects `DATABASE_URL` into your service.
4. Add `BOT_TOKEN` as an environment variable under **Variables**.
5. Railway uses the `Procfile` to run the bot as a **worker** process (no web server needed).

## Running tests

```bash
pip install -r requirements-dev.txt
pytest tests/
```

## Architecture

```
bot/
├── main.py          Entry point, Application setup
├── config.py        Load BOT_TOKEN and DATABASE_URL from environment
├── database.py      PostgreSQL access via asyncpg
├── models.py        Dataclasses: DebtRecord, PendingDebtState, PendingSettleState
├── currency.py      ISO 4217 validation + rapidfuzz fuzzy matching
├── formatting.py    Render debt summaries
└── handlers/
    ├── common.py    Shared helpers (member keyboard, arg parsing)
    ├── debt.py      /debt ConversationHandler
    ├── settle.py    /settle ConversationHandler
    ├── debts.py     /debts command
    └── help.py      /help + /start command
```
