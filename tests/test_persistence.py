"""Persistence tests: state must survive a process restart (SQLite store)."""

import os
import sqlite3

from database import (
    BAN_REPORT_THRESHOLD,
    ChatState,
    Database,
    Gender,
    GIRL_SEARCH_COST,
    REFERRAL_REWARD,
    STARTING_COINS,
)


def register(db, uid, gender=Gender.MALE, country="US", pref=Gender.ANY):
    user = db.register_user(uid)
    db.update_gender(uid, gender)
    db.update_country(uid, country)
    db.update_preferred_gender(uid, pref)
    return user


def test_default_is_memory_only_during_tests():
    assert os.environ.get("DB_PATH") == ""
    assert Database().path == ""


def test_state_survives_restart(tmp_path):
    path = str(tmp_path / "bot.db")

    db = Database(path=path)
    register(db, 1, gender=Gender.MALE, country="US")
    register(db, 2, gender=Gender.FEMALE, country="FR")
    db.add_coins(1, 40)
    db.spend_coins(1, 5)
    db.add_like(2, 1)
    db.apply_referral(1, 2)
    db.processed_charges.add("ch_123")
    db.add_to_queue(1, search_pref=Gender.FEMALE)
    db.close()

    db2 = Database(path=path)
    a, b = db2.get_user(1), db2.get_user(2)
    assert a is not None and b is not None
    assert a.username is None
    assert a.gender == Gender.MALE and a.country == "US"
    assert b.gender == Gender.FEMALE and b.country == "FR"
    assert a.coins == STARTING_COINS + 40 - 5 + REFERRAL_REWARD
    assert a.likes == 1
    assert a.liked_by == {2}
    assert a.referral_count == 1 and a.referred_by is None
    assert b.referred_by == 1
    assert db2.queue == [1]
    assert a.state == ChatState.SEARCHING
    assert a.search_pref == Gender.FEMALE
    assert db2.processed_charges == {"ch_123"}
    db2.close()


def test_search_filter_is_reset_on_restart_after_cancel(tmp_path):
    path = str(tmp_path / "bot.db")

    db = Database(path=path)
    register(db, 1)
    db.add_to_queue(1, search_pref=Gender.FEMALE)
    db.remove_from_queue(1)
    db.close()

    db2 = Database(path=path)
    assert db2.queue == []
    assert db2.get_user(1).state == ChatState.IDLE
    assert db2.get_user(1).search_pref is None
    db2.close()


def test_chat_session_survives_restart(tmp_path):
    path = str(tmp_path / "bot.db")

    db = Database(path=path)
    register(db, 1)
    register(db, 2, gender=Gender.FEMALE)
    db.add_to_queue(1)
    db.add_to_queue(2)
    db.pair_users(1, 2)
    db.close()

    db2 = Database(path=path)
    a, b = db2.get_user(1), db2.get_user(2)
    assert a.state == b.state == ChatState.CHATTING
    assert a.partner_id == 2 and b.partner_id == 1
    assert a.total_chats == 1 and db2.chatting_count == 1
    assert db2.queue == []
    db2.close()


def test_bans_and_blocks_survive_restart(tmp_path):
    path = str(tmp_path / "bot.db")

    db = Database(path=path)
    register(db, 1)
    for i in range(10, 10 + BAN_REPORT_THRESHOLD):
        register(db, i)
        db.add_report(i, 1)
    db.close()

    db2 = Database(path=path)
    assert db2.get_user(1).banned is True
    assert len(db2.get_user(1).reports) == BAN_REPORT_THRESHOLD
    assert db2.get_user(10).blocked == {1}
    db2.add_to_queue(1)
    assert db2.queue == []          # banned users stay out of the queue
    db2.close()


def test_coin_balance_is_not_lost_after_redeploy(tmp_path):
    path = str(tmp_path / "bot.db")

    db = Database(path=path)
    register(db, 1)
    db.add_coins(1, 6200)   # paid Stars package
    assert db.spend_coins(1, GIRL_SEARCH_COST) is True
    db.close()

    db2 = Database(path=path)
    assert db2.get_user(1).coins == STARTING_COINS + 6200 - GIRL_SEARCH_COST
    db2.close()


def test_corrupt_row_is_skipped_not_fatal(tmp_path):
    path = str(tmp_path / "bot.db")

    db = Database(path=path)
    register(db, 1)
    db.close()

    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT OR REPLACE INTO users(user_id, data) VALUES (?, ?)",
        (999, "{not valid json"),
    )
    conn.commit()
    conn.close()

    db2 = Database(path=path)
    assert db2.get_user(1) is not None
    assert db2.get_user(999) is None
    db2.close()


def test_queue_entry_for_deleted_user_is_dropped(tmp_path):
    path = str(tmp_path / "bot.db")

    db = Database(path=path)
    register(db, 1)
    db.add_to_queue(1)
    db.close()

    # Simulate a user row vanishing while still queued.
    conn = sqlite3.connect(path)
    conn.execute("DELETE FROM users WHERE user_id = 1")
    conn.commit()
    conn.close()

    db2 = Database(path=path)
    assert db2.queue == []
    db2.close()


def test_memory_mode_creates_no_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = Database(path="")
    assert db.path == ""
    db.register_user(1)
    db.close()
    assert list(tmp_path.iterdir()) == []
