import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.environ.get("BOT_TOKEN", "")
DATABASE_URL: str = os.environ.get("DATABASE_URL", "")

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set. "
        "Create a .env file with BOT_TOKEN=<your token> "
        "or set the environment variable directly."
    )

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. "
        "Create a .env file with DATABASE_URL=postgresql://... "
        "or set the environment variable directly."
    )
