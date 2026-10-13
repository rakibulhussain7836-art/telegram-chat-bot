"""Shared test setup — makes the project root importable and provides a clean bot DB."""

import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Tests must never touch a real SQLite file (set before database.py is imported).
os.environ["DB_PATH"] = ""
# Keep the suite fast and deterministic — no frame-by-frame animations.
os.environ["BOT_ANIMATIONS"] = "0"
# Backup targets must never be REAL: load_dotenv() would otherwise pull the
# developer's .env in and tests would send files to live Telegram/GitHub.
os.environ["BACKUP_CHANNEL"] = ""
os.environ["BACKUP_BOT_TOKEN"] = ""
os.environ["BACKUP_GITHUB_REPO"] = ""
os.environ["BACKUP_GITHUB_TOKEN"] = ""


@pytest.fixture
def fresh_db():
    """Reset the singleton database used by bot.py before and after each test."""
    import bot

    def clear():
        bot.db.users.clear()
        bot.db.queue.clear()
        bot.db.processed_charges.clear()
        bot.db.requests.clear()
        bot.db.pending_verifications.clear()
        bot.db.pending_dms.clear()
        bot.db._by_public_id.clear()

    clear()
    yield bot.db
    clear()
