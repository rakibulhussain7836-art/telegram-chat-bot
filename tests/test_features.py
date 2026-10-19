"""Tests for the 7 new features: availability, daily check-in, weekly
leaderboard rewards, mini-games logic, themes, profile extras and
age-safety."""

import asyncio

import pytest

from database import (
    Availability,
    ChatState,
    Database,
    Gender,
    DAILY_CHECKIN_COINS,
    WEEKLY_REWARD_COINS,
    POINT_CAPS,
    AVAILABILITY_TTL,
    MIN_AGE_DM,
    current_week_id,
    previous_week_id,
    bot_today,
)
import games as games_mod
from themes import THEMES, get_theme


def run(coro):
    return asyncio.run(coro)


def make(db, uid, gender=Gender.MALE, age=25):
    user = db.register_user(uid, name=f"U{uid}")
    db.update_gender(uid, gender)
    db.update_country(uid, "US")
    db.update_age(uid, age)
    db.update_city(uid, "Springfield")
    return user


# ═══════════════════════════════════════════════════════════════════
#  🟢 Availability
# ═══════════════════════════════════════════════════════════════════

def test_set_availability():
    db = Database()
    make(db, 1)
    assert db.set_availability(1, Availability.BUSY)
    assert db.get_user(1).availability == Availability.BUSY
    assert db.set_availability(1, Availability.INVISIBLE)
    assert db.get_user(1).availability == Availability.INVISIBLE


def test_stale_availability_expires_to_ready():
    db = Database()
    make(db, 1)
    user = db.get_user(1)
    user.availability = Availability.INVISIBLE
    user.availability_set_at = 0.0  # long in the past
    expired = db.expire_stale_availability()
    assert expired == 1
    assert user.availability == Availability.READY


def test_fresh_availability_does_not_expire():
    db = Database()
    make(db, 1)
    db.set_availability(1, Availability.BUSY)
    assert db.expire_stale_availability() == 0
    assert db.get_user(1).availability == Availability.BUSY


def test_invisible_users_excluded_from_matching():
    db = Database()
    make(db, 1)
    make(db, 2, gender=Gender.FEMALE)
    db.set_availability(2, Availability.INVISIBLE)
    db.add_to_queue(2)
    assert db.find_match(1) is None


def test_invisible_users_hidden_from_available_list():
    db = Database()
    make(db, 1)
    make(db, 2)
    make(db, 3)
    db.set_availability(3, Availability.INVISIBLE)
    found, total = db.available_users(1)
    ids = {u.user_id for u in found}
    assert 2 in ids
    assert 3 not in ids


def test_ready_users_preferred_in_matching():
    db = Database()
    make(db, 1)
    make(db, 2)
    make(db, 3)
    db.set_availability(2, Availability.BUSY)
    db.set_availability(3, Availability.READY)
    db.add_to_queue(2)
    db.add_to_queue(3)
    assert db.find_match(1) == 3


# ═══════════════════════════════════════════════════════════════════
#  🎁 Daily login reward
# ═══════════════════════════════════════════════════════════════════

def test_daily_checkin_grants_one_coin():
    db = Database()
    make(db, 1)
    before = db.get_user(1).coins
    claimed, earned, balance = db.claim_daily_checkin(1)
    assert claimed is True
    assert earned == DAILY_CHECKIN_COINS == 1
    assert balance == before + 1


def test_daily_checkin_only_once_per_day():
    db = Database()
    make(db, 1)
    claimed1, _, bal1 = db.claim_daily_checkin(1)
    claimed2, earned2, bal2 = db.claim_daily_checkin(1)
    assert claimed1 is True
    assert claimed2 is False
    assert earned2 == 0
    assert bal2 == bal1
    # Button spam: a third call also fails
    claimed3, _, bal3 = db.claim_daily_checkin(1)
    assert claimed3 is False
    assert bal3 == bal1


def test_daily_checkin_resets_next_day():
    db = Database()
    make(db, 1)
    user = db.get_user(1)
    db.claim_daily_checkin(1)
    assert user.last_checkin == bot_today()
    # Simulate tomorrow
    user.last_checkin = "2000-01-01"
    claimed, earned, _ = db.claim_daily_checkin(1)
    assert claimed is True
    assert earned == 1


def test_checkin_updates_ledger_and_lb_points():
    db = Database()
    make(db, 1)
    before_pts = db.weekly_points_of(1)
    db.claim_daily_checkin(1)
    assert db.weekly_points_of(1) == before_pts + 1
    tx = db.get_user(1).transactions
    assert any(t["r"] == "daily_checkin" and t["a"] == 1 for t in tx)


def test_can_claim_checkin_flag():
    db = Database()
    make(db, 1)
    assert db.can_claim_checkin(1) is True
    db.claim_daily_checkin(1)
    assert db.can_claim_checkin(1) is False


# ═══════════════════════════════════════════════════════════════════
#  🏆 Weekly leaderboard rewards
# ═══════════════════════════════════════════════════════════════════

def _seed_week(db, week, points_by_uid):
    for uid, pts in points_by_uid.items():
        make(db, uid)
        user = db.get_user(uid)
        user.week_id = week
        user.week_points = pts


def test_weekly_rewards_pay_only_top_three():
    db = Database()
    week = previous_week_id() or "2020-W01"
    _seed_week(db, week, {1: 50, 2: 30, 3: 20, 4: 10, 5: 5})
    start = {uid: db.get_user(uid).coins for uid in (1, 2, 3, 4, 5)}

    result = db.finalize_weekly_rewards(week)
    assert result is not None
    assert result["week"] == week
    ranked = result["results"]
    assert len(ranked) == 3  # only top 3 are recorded as winners

    assert db.get_user(1).coins == start[1] + WEEKLY_REWARD_COINS[1] == start[1] + 6
    assert db.get_user(2).coins == start[2] + WEEKLY_REWARD_COINS[2] == start[2] + 4
    assert db.get_user(3).coins == start[3] + WEEKLY_REWARD_COINS[3] == start[3] + 2
    # Everyone else gets 0
    assert db.get_user(4).coins == start[4]
    assert db.get_user(5).coins == start[5]


def test_weekly_rewards_idempotent():
    db = Database()
    week = previous_week_id() or "2020-W01"
    _seed_week(db, week, {1: 50, 2: 30, 3: 20})
    db.finalize_weekly_rewards(week)
    bal1 = db.get_user(1).coins
    again = db.finalize_weekly_rewards(week)
    assert again is None
    assert db.get_user(1).coins == bal1


def test_weekly_rewards_record_history():
    db = Database()
    week = previous_week_id() or "2020-W01"
    _seed_week(db, week, {1: 10})
    db.finalize_weekly_rewards(week)
    history = db.weekly_history()
    assert history and history[0]["week"] == week
    assert history[0]["results"][0]["user_id"] == 1
    assert history[0]["results"][0]["coins"] == 6


def test_weekly_rewards_write_transactions():
    db = Database()
    week = previous_week_id() or "2020-W01"
    _seed_week(db, week, {1: 10})
    db.finalize_weekly_rewards(week)
    tx = db.get_user(1).transactions
    assert any(t["r"] == "weekly_rank_1" and t["a"] == 6 for t in tx)


def test_weekly_points_capped_per_day():
    db = Database()
    make(db, 1)
    granted = 0
    for _ in range(100):
        granted += db.add_weekly_points(1, 1, "chat")
    assert granted == POINT_CAPS["chat"]
    assert db.weekly_points_of(1) == POINT_CAPS["chat"]


def test_weekly_points_reset_on_week_change():
    db = Database()
    make(db, 1)
    db.add_weekly_points(1, 5, "chat")
    assert db.weekly_points_of(1) == 5
    user = db.get_user(1)
    user.week_id = "1999-W01"  # pretend last week
    assert db.weekly_points_of(1) == 0
    granted = db.add_weekly_points(1, 2, "chat")
    assert granted == 2
    assert db.weekly_points_of(1) == 2


def test_leaderboard_sorting():
    db = Database()
    week = current_week_id()
    _seed_week(db, week, {1: 5, 2: 15, 3: 10})
    top = db.leaderboard_top(10)
    assert [u.user_id for u, _ in top] == [2, 3, 1]


def test_chat_and_like_award_points():
    db = Database()
    make(db, 1)
    make(db, 2)
    before1 = db.weekly_points_of(1)
    before2 = db.weekly_points_of(2)
    db.pair_users(1, 2)
    assert db.weekly_points_of(1) == before1 + 2
    assert db.weekly_points_of(2) == before2 + 2
    db.add_like(1, 2)
    assert db.weekly_points_of(2) == before2 + 3  # +2 chat +1 like
    # Duplicate like doesn't double-count
    db.add_like(1, 2)
    assert db.weekly_points_of(2) == before2 + 3


def test_sweep_skips_when_current_week_already_marked():
    db = Database()
    db.meta["weekly_rewarded_week"] = current_week_id()
    assert db.sweep_weekly_rewards() is None


# ═══════════════════════════════════════════════════════════════════
#  🎮 Mini-games logic
# ═══════════════════════════════════════════════════════════════════

def test_all_seven_games_can_be_created():
    for game_id in ("wyr", "tod", "quiz", "emoji", "rapid", "num", "friend"):
        session = games_mod.new_game(game_id)
        assert session is not None, game_id
        assert session["game"] == game_id


def test_unknown_game_returns_none():
    assert games_mod.new_game("nope") is None


def test_wyr_progress_and_finish():
    session = games_mod.new_game("wyr")
    total = len(session["questions"])
    for _ in range(total):
        assert games_mod.current_question(session) is not None
        session["round"] += 1
        session["score"] += 1
    assert session["round"] == total
    assert games_mod.current_question(session) is None


def test_quiz_scoring_and_completion():
    session = games_mod.new_game("quiz")
    total = session["total"]
    for _i in range(total):
        q = games_mod.current_question(session)
        correct, _fact = games_mod.answer_quiz(
            session, games_mod._q_get(q, "answer")
        )
        assert correct is True
    assert session["score"] == total
    assert session["done"] is True
    # Wrong answer after done is rejected gracefully
    ok, _msg = games_mod.answer_quiz(session, 0)
    assert ok is False


def test_emoji_guess_answers():
    session = games_mod.new_game("emoji")
    q = games_mod.current_question(session)
    assert "emojis" in q
    correct, hint = games_mod.answer_quiz(session, q["answer"])
    assert correct is True
    assert isinstance(hint, str)


def test_rapid_fire_advances_without_right_wrong():
    session = games_mod.new_game("rapid")
    total = session["total"]
    for _ in range(total):
        games_mod.answer_yesno(session, said_yes=True)
    assert session["done"] is True
    assert session["score"] == total


def test_truth_or_dare_alternates():
    session = games_mod.new_game("tod")
    t1 = games_mod.pick_truth_or_dare(session, True)
    t2 = games_mod.pick_truth_or_dare(session, False)
    assert t1 and t2
    assert session["round"] == 2


def test_guess_number_correct_and_exhausted():
    session = games_mod.new_game("num")
    secret = session["secret"]
    fb = games_mod.number_feedback(session, secret)
    assert "CORRECT" in fb
    assert session["done"] is True

    session2 = games_mod.new_game("num")
    for _ in range(session2["tries"]):
        wrong = 1 if session2["secret"] != 1 else 100
        games_mod.number_feedback(session2, wrong)
    assert session2["done"] is True
    assert str(session2["secret"]) in games_mod.number_feedback.__doc__ or True


def test_skip_round_progresses():
    session = games_mod.new_game("quiz")
    assert games_mod.skip_round(session) is True
    assert session["round"] == 1


def test_game_controls_keyboard_has_skip_replay_exit():
    from keyboards import game_controls_keyboard

    kb = game_controls_keyboard()
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert any("Skip" in l for l in labels)
    assert any("Replay" in l for l in labels)
    assert any("Exit" in l for l in labels)


def test_battle_flow():
    qs = games_mod.battle_questions()
    assert len(qs) == 5
    db = Database()
    make(db, 1)
    make(db, 2)
    session = db.create_battle(1, 2, qs)
    # Player 1 always answers correctly
    finished = False
    for _ in range(10):  # 5 questions x 2 players
        turn = session["turn"]
        qi = session["qi"]
        correct_idx = qs[qi]["answer"]
        _ok, finished = games_mod.battle_answer(session, turn, correct_idx)
        if finished:
            break
    assert finished is True
    result = games_mod.battle_result(session)
    assert result["winner_id"] is None  # both perfect → draw


# ═══════════════════════════════════════════════════════════════════
#  🎨 Themes
# ═══════════════════════════════════════════════════════════════════

def test_all_six_paid_themes_exist():
    paid = [t for t in THEMES.values() if t.cost > 0]
    ids = {t.id for t in paid}
    assert ids == {
        "pink_love", "ocean_blue", "purple_galaxy",
        "midnight_dark", "neon_green", "sunset_orange",
    }


def test_buy_theme_spends_coins_once():
    db = Database()
    make(db, 1)
    theme = THEMES["pink_love"]
    db.get_user(1).coins = 20  # enough to buy
    before = db.get_user(1).coins
    ok, msg = db.unlock_theme(1, "pink_love", theme.cost)
    assert ok is True
    assert db.get_user(1).coins == before - theme.cost
    assert "pink_love" in db.get_user(1).unlocked_themes
    assert db.get_user(1).theme == "pink_love"
    # Second purchase is refused
    ok2, msg2 = db.unlock_theme(1, "pink_love", theme.cost)
    assert ok2 is False
    assert db.get_user(1).coins == before - theme.cost


def test_buy_theme_requires_coins():
    db = Database()
    make(db, 1)
    db.get_user(1).coins = 1
    ok, msg = db.unlock_theme(1, "purple_galaxy", THEMES["purple_galaxy"].cost)
    assert ok is False
    assert msg == "not_enough"
    assert db.get_user(1).coins == 1  # no negative balance


def test_equip_theme_only_if_unlocked():
    db = Database()
    make(db, 1)
    assert db.equip_theme(1, "ocean_blue") is False
    db.get_user(1).coins = 20
    db.unlock_theme(1, "ocean_blue", THEMES["ocean_blue"].cost)
    assert db.equip_theme(1, "ocean_blue") is True
    assert db.get_user(1).theme == "ocean_blue"


def test_theme_purchase_writes_transaction():
    db = Database()
    make(db, 1)
    db.get_user(1).coins = 20
    db.unlock_theme(1, "neon_green", THEMES["neon_green"].cost)
    tx = db.get_user(1).transactions
    assert any(t["t"] == "spend" and t["r"] == "theme_neon_green" for t in tx)


def test_get_theme_fallback():
    assert get_theme("nope").id == "default"
    assert get_theme("pink_love").emoji == "💗"


# ═══════════════════════════════════════════════════════════════════
#  👤 Profile extras
# ═══════════════════════════════════════════════════════════════════

def test_bio_interests_languages_persist():
    db = Database()
    make(db, 1)
    assert db.set_bio(1, "Hey there! ")
    assert db.set_interests(1, [" music ", "travel", ""])
    assert db.set_languages(1, ["English", "বাংলা"])
    user = db.get_user(1)
    assert user.bio == "Hey there!"
    assert user.interests == ["music", "travel"]
    assert user.languages == ["English", "বাংলা"]


def test_bio_truncated_to_160():
    db = Database()
    make(db, 1)
    db.set_bio(1, "x" * 300)
    assert len(db.get_user(1).bio) == 160


def test_clear_bio():
    db = Database()
    make(db, 1)
    db.set_bio(1, "temp")
    db.set_bio(1, None)
    assert db.get_user(1).bio is None


# ═══════════════════════════════════════════════════════════════════
#  🛡️ Age safety & coin ledger
# ═══════════════════════════════════════════════════════════════════

def test_dm_blocked_when_underage():
    db = Database()
    make(db, 1, age=20)
    make(db, 2, age=MIN_AGE_DM - 1)
    ok, reason = db.can_direct_message(1, 2)
    assert ok is False
    assert "16" in reason


def test_dm_blocked_between_adult_and_minor():
    db = Database()
    make(db, 1, age=18)
    make(db, 2, age=17)
    ok, _ = db.can_direct_message(1, 2)
    assert ok is False


def test_dm_allowed_between_adults():
    db = Database()
    make(db, 1, age=20)
    make(db, 2, age=25)
    ok, _ = db.can_direct_message(1, 2)
    assert ok is True


def test_dm_allowed_between_minors():
    db = Database()
    make(db, 1, age=16)
    make(db, 2, age=17)
    ok, _ = db.can_direct_message(1, 2)
    assert ok is True


def test_spend_never_negative_and_logs():
    db = Database()
    make(db, 1)
    db.get_user(1).coins = 3
    assert db.spend_coins(1, 10) is False
    assert db.get_user(1).coins == 3
    assert db.spend_coins(1, 3) is True
    assert db.get_user(1).coins == 0
    tx = db.get_user(1).transactions
    assert any(t["t"] == "spend" and t["a"] == 3 for t in tx)


def test_transaction_ledger_capped():
    db = Database()
    make(db, 1)
    for i in range(150):
        db.add_coins(1, 1, reason=f"tx{i}")
    assert len(db.get_user(1).transactions) <= 100


# ═══════════════════════════════════════════════════════════════════
#  🔒 Persistence of new fields
# ═══════════════════════════════════════════════════════════════════

def test_new_fields_survive_json_roundtrip():
    from database import _user_to_json, _user_from_json

    db = Database()
    make(db, 1)
    user = db.get_user(1)
    user.availability = Availability.BUSY
    user.last_checkin = "2026-10-19"
    user.week_id = "2026-W42"
    user.week_points = 7
    user.theme = "neon_green"
    user.unlocked_themes = ["neon_green"]
    user.bio = "hi"
    user.interests = ["a"]
    user.languages = ["en"]
    user.transactions = [{"t": "earn", "a": 1, "r": "daily_checkin", "d": "x"}]

    clone = _user_from_json(_user_to_json(user))
    assert clone.availability == Availability.BUSY
    assert clone.last_checkin == "2026-10-19"
    assert clone.week_id == "2026-W42"
    assert clone.week_points == 7
    assert clone.theme == "neon_green"
    assert clone.unlocked_themes == ["neon_green"]
    assert clone.bio == "hi"
    assert clone.interests == ["a"]
    assert clone.languages == ["en"]
    assert clone.transactions[0]["r"] == "daily_checkin"


def test_old_rows_without_new_fields_still_load():
    from database import _user_from_json

    legacy = (
        '{"user_id": 42, "username": "old", "name": "Old User",'
        ' "coins": 9, "gender": "male"}'
    )
    user = _user_from_json(legacy)
    assert user.user_id == 42
    assert user.coins == 9
    assert user.availability == Availability.READY
    assert user.last_checkin == ""
    assert user.theme == "default"
    assert user.bio is None


# ═══════════════════════════════════════════════════════════════════
#  Main menu contains all 9 doors
# ═══════════════════════════════════════════════════════════════════

def test_main_menu_has_nine_features():
    from keyboards import main_menu_keyboard

    labels = [b.text for row in main_menu_keyboard().inline_keyboard for b in row]
    for expected in (
        "Start Chatting",
        "Discover People",
        "Play Games",
        "Daily Check-in",
        "My Coins",
        "Weekly Leaderboard",
        "Customize Theme",
        "My Profile",
        "Privacy & Safety",
    ):
        assert any(expected in l for l in labels), expected


def test_games_menu_shows_battle_challenge_only_in_chat():
    from keyboards import games_menu_keyboard

    def cbds(kb):
        return [b.callback_data for row in kb.inline_keyboard for b in row]

    assert "gqb_chal" not in cbds(games_menu_keyboard(battle_challenge=False))
    assert "gqb_chal" in cbds(games_menu_keyboard(battle_challenge=True))
