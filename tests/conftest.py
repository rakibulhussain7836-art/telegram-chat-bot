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


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "no_auto_checkin: opt out of the autouse daily check-in claim "
        "(for tests that verify the gate itself)",
    )


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
        bot.db.game_battles.clear()
        bot.db.meta.clear()
        bot.db._by_public_id.clear()
        # Force-join answers must never leak between tests
        bot._MEMBER_CACHE.clear()
        # 🗑 chat logs are keyed by user id — they must not survive a reset
        bot._CHAT_LOGS.clear()
        # 🏆 per-user message-point buckets must not survive a reset
        bot._MSG_POINT_BUCKET.clear()

    clear()
    yield bot.db
    clear()


@pytest.fixture
def auto_checkin(fresh_db):
    """
    🎁 MANDATORY daily check-in is a real product rule, but most tests are
    about something else. This helper makes it trivial to satisfy: after a
    user exists, claim today's check-in for them.

    Tests that want to exercise the gate itself can monkeypatch this
    fixture away or use ``auto_checkin.off()``.
    """
    import bot
    from database import bot_today

    class _Auto:
        def __init__(self):
            self._active = True

        def off(self):
            self._active = False

        def claim(self, user_id):
            user = bot.db.get_user(user_id)
            if user:
                user.last_checkin = bot_today()

    auto = _Auto()
    yield auto


@pytest.fixture(autouse=True)
def _claim_checkins(request, fresh_db):
    """Auto-claim today's check-in for every user in every test by default.

    The daily check-in is mandatory to earn coins/points, but most tests
    are about something else — so we satisfy the rule automatically for
    every Database instance (``bot.db`` and any locally-constructed one).

    Opt out with ``@pytest.mark.no_auto_checkin`` (for tests that verify
    the gate itself).
    """
    if request.node.get_closest_marker("no_auto_checkin"):
        yield
        return

    import database
    from database import bot_today

    original = database.Database.register_user

    def wrapper(self, *args, **kwargs):
        user = original(self, *args, **kwargs)
        if user:
            user.last_checkin = bot_today()
        return user

    database.Database.register_user = wrapper
    yield
    database.Database.register_user = original
