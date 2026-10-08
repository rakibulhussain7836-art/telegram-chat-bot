"""Unit tests for the in-memory database: economy, referrals, likes, moderation, matchmaking."""

from database import (
    BAN_REPORT_THRESHOLD,
    ChatState,
    Database,
    Gender,
    GIRL_SEARCH_COST,
    CHAT_REQUEST_COST,
    NEARBY_RADIUS_KM,
    REFERRED_BONUS,
    REFERRAL_REWARD,
    STARTING_COINS,
)


def make_user(db, uid, gender=None, country=None, pref=Gender.ANY):
    user = db.register_user(uid)
    if gender:
        db.update_gender(uid, gender)
    if country:
        db.update_country(uid, country)
    db.update_preferred_gender(uid, pref)
    return user


# ── Users ────────────────────────────────────────────────────────

def test_new_user_gets_starting_coins():
    db = Database()
    user = db.register_user(1, "alice")
    assert user.coins == STARTING_COINS
    assert user.state == ChatState.IDLE


def test_register_is_idempotent_and_updates_username():
    db = Database()
    first = db.register_user(1, "alice")
    second = db.register_user(1, "alice_new")
    assert first is second
    assert second.username == "alice_new"
    assert second.coins == STARTING_COINS


def test_get_user_returns_none_for_unknown():
    assert Database().get_user(999) is None


# ── Coins ────────────────────────────────────────────────────────

def test_add_and_spend_coins():
    db = Database()
    db.register_user(1)
    assert db.add_coins(1, 50) == STARTING_COINS + 50
    assert db.spend_coins(1, 5) is True
    assert db.get_user(1).coins == STARTING_COINS + 45


def test_spend_coins_fails_without_balance():
    db = Database()
    db.register_user(1)
    assert db.spend_coins(1, STARTING_COINS + 1) is False
    assert db.get_user(1).coins == STARTING_COINS
    assert db.spend_coins(404, 1) is False


def test_balance_never_goes_negative():
    db = Database()
    db.register_user(1)
    db.add_coins(1, -10_000)
    assert db.get_user(1).coins == 0


# ── Referrals ────────────────────────────────────────────────────

def test_referral_pays_both_sides_once():
    db = Database()
    make_user(db, 1)
    make_user(db, 2)

    gains = db.apply_referral(1, 2)
    assert gains == (REFERRAL_REWARD, REFERRED_BONUS)
    assert db.get_user(1).coins == STARTING_COINS + REFERRAL_REWARD
    assert db.get_user(2).coins == STARTING_COINS + REFERRED_BONUS
    assert db.get_user(1).referral_count == 1
    assert db.get_user(2).referred_by == 1

    assert db.apply_referral(1, 2) is None
    assert db.get_user(1).coins == STARTING_COINS + REFERRAL_REWARD


def test_self_referral_is_ignored():
    db = Database()
    make_user(db, 1)
    assert db.apply_referral(1, 1) is None
    assert db.get_user(1).coins == STARTING_COINS


def test_banned_referrer_earns_nothing():
    db = Database()
    make_user(db, 1)
    make_user(db, 2)
    for reporter in (10, 11, 12, 13, 14):
        make_user(db, reporter)
        db.add_report(reporter, 1)
    assert db.get_user(1).banned is True

    assert db.apply_referral(1, 2) is None
    assert db.get_user(2).referred_by is None
    assert db.get_user(2).coins == STARTING_COINS


# ── Likes ────────────────────────────────────────────────────────

def test_like_counts_only_once():
    db = Database()
    make_user(db, 1)
    make_user(db, 2)

    assert db.add_like(1, 2) == (True, 1)
    assert db.add_like(1, 2) == (False, 1)
    assert db.get_user(2).likes == 1
    assert len(db.likers_of(2)) == 1


def test_self_like_and_unknown_target_rejected():
    db = Database()
    make_user(db, 1)
    assert db.add_like(1, 1) == (False, 0)
    assert db.add_like(1, 999) == (False, 0)


def test_likers_of_unknown_user_is_empty():
    assert Database().likers_of(123) == []


# ── Reports / bans ───────────────────────────────────────────────

def test_ban_triggers_at_threshold():
    db = Database()
    make_user(db, 1)
    banned = False
    for i in range(2, 2 + BAN_REPORT_THRESHOLD):
        make_user(db, i)
        banned = db.add_report(i, 1)
    assert banned is True
    assert db.get_user(1).banned is True


def test_duplicate_report_from_same_user_does_not_count():
    db = Database()
    make_user(db, 1)
    make_user(db, 2)
    for _ in range(BAN_REPORT_THRESHOLD):
        assert db.add_report(2, 1) is False
    assert db.get_user(1).banned is False


def test_report_blocks_future_matching():
    db = Database()
    make_user(db, 1, gender=Gender.MALE, country="US")
    make_user(db, 2, gender=Gender.FEMALE, country="US")
    db.add_to_queue(1, search_pref=None)
    db.add_to_queue(2, search_pref=None)
    assert db.find_match(1) == 2

    assert db.add_report(1, 2) is False
    assert db.find_match(1) is None


def test_self_report_is_rejected():
    db = Database()
    make_user(db, 1)
    assert db.add_report(1, 1) is False


# ── Queue / matchmaking ─────────────────────────────────────────

def test_queue_sets_and_clears_search_state():
    db = Database()
    make_user(db, 1)
    db.add_to_queue(1, search_pref=Gender.FEMALE)
    assert db.get_user(1).state == ChatState.SEARCHING
    assert db.get_user(1).search_pref == Gender.FEMALE
    assert db.searching_count == 1

    db.remove_from_queue(1)
    assert db.get_user(1).state == ChatState.IDLE
    assert db.get_user(1).search_pref is None
    assert db.searching_count == 0


def test_user_is_only_queued_once():
    db = Database()
    make_user(db, 1)
    db.add_to_queue(1)
    db.add_to_queue(1)
    assert db.queue == [1]


def test_banned_user_cannot_enter_queue():
    db = Database()
    make_user(db, 1)
    make_user(db, 2)
    for i in range(3, 3 + BAN_REPORT_THRESHOLD):
        make_user(db, i)
        db.add_report(i, 1)
    db.add_to_queue(1)
    assert db.queue == []
    assert db.find_match(1) is None


def test_no_match_when_alone_in_queue():
    db = Database()
    make_user(db, 1)
    db.add_to_queue(1)
    assert db.find_match(1) is None


def test_gender_filter_is_respected_both_ways():
    db = Database()
    make_user(db, 1, gender=Gender.MALE, pref=Gender.FEMALE)   # only wants women
    make_user(db, 2, gender=Gender.MALE, pref=Gender.ANY)
    make_user(db, 3, gender=Gender.FEMALE, pref=Gender.MALE)   # only wants men
    db.add_to_queue(1, search_pref=None)
    db.add_to_queue(2, search_pref=None)
    db.add_to_queue(3, search_pref=None)

    assert db.find_match(1) == 3   # skips the other man
    assert db.find_match(2) == 3   # anyone, but 1 rejects men
    assert db.find_match(3) == 1   # skips the other woman


def test_per_search_girl_filter_only_matches_women():
    db = Database()
    make_user(db, 1, gender=Gender.MALE, pref=Gender.ANY)
    make_user(db, 2, gender=Gender.MALE, pref=Gender.ANY)
    make_user(db, 3, gender=Gender.FEMALE, pref=Gender.ANY)
    db.add_to_queue(2, search_pref=None)
    db.add_to_queue(3, search_pref=None)
    db.add_to_queue(1, search_pref=Gender.FEMALE)

    assert db.find_match(1) == 3


def test_cross_country_matches_are_preferred():
    db = Database()
    make_user(db, 1, gender=Gender.MALE, country="US", pref=Gender.ANY)
    make_user(db, 2, gender=Gender.FEMALE, country="US", pref=Gender.ANY)
    make_user(db, 3, gender=Gender.FEMALE, country="FR", pref=Gender.ANY)
    db.add_to_queue(2, search_pref=None)
    db.add_to_queue(3, search_pref=None)
    db.add_to_queue(1, search_pref=None)

    assert db.find_match(1) == 3


def test_banned_candidate_is_skipped():
    db = Database()
    make_user(db, 1, gender=Gender.MALE, pref=Gender.ANY)
    make_user(db, 2, gender=Gender.FEMALE, pref=Gender.ANY)
    db.add_to_queue(1, search_pref=None)
    db.add_to_queue(2, search_pref=None)
    for i in range(3, 3 + BAN_REPORT_THRESHOLD):
        make_user(db, i)
        db.add_report(i, 2)
    assert db.get_user(2).banned is True
    assert db.find_match(1) is None


# ── Chat sessions ────────────────────────────────────────────────

def test_pair_users_starts_chat_for_both():
    db = Database()
    make_user(db, 1)
    make_user(db, 2)
    db.add_to_queue(1)
    db.add_to_queue(2)
    db.pair_users(1, 2)

    a, b = db.get_user(1), db.get_user(2)
    assert a.state == b.state == ChatState.CHATTING
    assert a.partner_id == 2 and b.partner_id == 1
    assert a.total_chats == 1 and b.total_chats == 1
    assert db.searching_count == 0
    assert db.chatting_count == 1


def test_end_chat_resets_both_partners():
    db = Database()
    make_user(db, 1)
    make_user(db, 2)
    db.add_to_queue(1)
    db.add_to_queue(2)
    db.pair_users(1, 2)

    assert db.end_chat(1) == 2
    a, b = db.get_user(1), db.get_user(2)
    assert a.state == b.state == ChatState.IDLE
    assert a.partner_id is None and b.partner_id is None
    assert db.chatting_count == 0


def test_end_chat_outside_chat_returns_none():
    db = Database()
    make_user(db, 1)
    assert db.end_chat(1) is None
    assert db.end_chat(404) is None


def test_counters():
    db = Database()
    make_user(db, 1)
    make_user(db, 2)
    make_user(db, 3)
    db.add_to_queue(3)
    db.add_to_queue(1)
    db.add_to_queue(2)
    db.pair_users(1, 2)

    assert db.online_count == 3
    assert db.searching_count == 1
    assert db.chatting_count == 1


def test_girl_search_is_not_free():
    assert GIRL_SEARCH_COST >= 1


# ── Public IDs ──────────────────────────────────────────────────

def test_every_user_gets_a_six_digit_public_id():
    db = Database()
    ids = {make_user(db, i).public_id for i in range(1, 30)}
    assert all(100000 <= pid <= 999999 for pid in ids)
    assert len(ids) == 29  # unique


def test_find_by_public_id_and_resolve_id():
    db = Database()
    user = make_user(db, 1)
    assert db.find_by_public_id(user.public_id) is user
    assert db.resolve_id(str(user.public_id)) is user
    assert db.resolve_id(1) is user          # Telegram user ID also works
    assert db.resolve_id(424242) is None
    assert db.resolve_id("abc") is None


# ── Nearby / location ───────────────────────────────────────────

def test_distance_is_computed_in_km():
    db = Database()
    make_user(db, 1)
    make_user(db, 2)
    db.set_location(1, 0.0, 0.0)
    db.set_location(2, 0.0, 1.0)   # ~111 km at the equator
    distance = db.distance_km(1, 2)
    assert distance is not None
    assert 100 < distance < 125


def test_nearby_sorts_by_distance_and_respects_radius():
    db = Database()
    make_user(db, 1)
    db.set_location(1, 0.0, 0.0)
    for uid, lon in ((2, 0.10), (3, 0.02), (4, 5.0)):   # ~11km, ~2km, ~550km
        make_user(db, uid)
        db.set_location(uid, 0.0, lon)

    results = db.nearby_users(1)
    assert [u.user_id for u, _ in results] == [3, 2]      # nearest first
    assert all(dist <= NEARBY_RADIUS_KM for _, dist in results)


def test_nearby_skips_users_without_location_and_self():
    db = Database()
    make_user(db, 1)
    db.set_location(1, 0.0, 0.0)
    make_user(db, 2)                       # never shared a location
    make_user(db, 3)
    db.set_location(3, 0.0, 0.1)

    assert [u.user_id for u, _ in db.nearby_users(1)] == [3]


def test_nearby_without_own_location_is_empty():
    db = Database()
    make_user(db, 1)
    make_user(db, 2)
    db.set_location(2, 0.0, 0.0)
    assert db.nearby_users(1) == []
    assert db.has_location(1) is False


# ── Contacts ────────────────────────────────────────────────────

def test_add_and_remove_contact():
    db = Database()
    make_user(db, 1)
    make_user(db, 2)
    assert db.add_contact(1, 2) is True
    assert db.add_contact(1, 2) is False        # already there
    assert [u.user_id for u in db.contacts_of(1)] == [2]
    assert db.remove_contact(1, 2) is True
    assert db.remove_contact(1, 2) is False
    assert db.contacts_of(1) == []


def test_cannot_add_self_or_unknown_as_contact():
    db = Database()
    make_user(db, 1)
    assert db.add_contact(1, 1) is False
    assert db.add_contact(1, 999) is False


# ── Like / unlike ───────────────────────────────────────────────

def test_unlike_removes_the_like():
    db = Database()
    make_user(db, 1)
    make_user(db, 2)
    db.add_like(1, 2)
    assert db.unlike(1, 2) == (True, 0)
    assert db.get_user(2).likes == 0
    assert db.unlike(1, 2) == (False, 0)
    assert db.likers_of(2) == []


def test_repeated_like_after_unlike_counts_once():
    db = Database()
    make_user(db, 1)
    make_user(db, 2)
    db.add_like(1, 2)
    db.unlike(1, 2)
    db.add_like(1, 2)
    assert db.get_user(2).likes == 1
    assert len(db.likers_of(2)) == 1


# ── Chat requests ───────────────────────────────────────────────

def test_request_charges_one_coin():
    db = Database()
    make_user(db, 1)
    make_user(db, 2)
    before = db.get_user(1).coins
    assert db.create_request(1, 2) == (True, "ok")
    assert db.get_user(1).coins == before - CHAT_REQUEST_COST
    assert db.request_status(1, 2) == "pending"


def test_request_fails_without_coins():
    db = Database()
    user = make_user(db, 1)
    make_user(db, 2)
    user.coins = 0
    ok, reason = db.create_request(1, 2)
    assert ok is False
    assert "Not enough Coins" in reason
    assert db.request_status(1, 2) is None
    assert user.coins == 0


def test_duplicate_and_reversed_requests_are_blocked():
    db = Database()
    make_user(db, 1)
    make_user(db, 2)
    assert db.create_request(1, 2)[0] is True
    balance = db.get_user(1).coins

    assert db.create_request(1, 2)[0] is False       # duplicate
    assert db.get_user(1).coins == balance            # not charged twice
    assert db.create_request(2, 1)[0] is False        # they already got one
    assert db.request_status(2, 1) is None


def test_self_and_banned_requests_are_blocked():
    db = Database()
    make_user(db, 1)
    make_user(db, 2)
    assert db.create_request(1, 1)[0] is False
    db.get_user(1).banned = True
    assert db.create_request(1, 2)[0] is False


def test_resolving_requests():
    db = Database()
    make_user(db, 1)
    make_user(db, 2)
    db.create_request(1, 2)
    assert db.resolve_request(1, 2, accepted=True) is True
    assert db.request_status(1, 2) == "accepted"
    assert db.resolve_request(1, 2, accepted=True) is False   # already resolved
    assert db.cancel_request(1, 2) is False                   # still stored
    assert db.cancel_request(9, 9) is False


def test_cancel_pending_request():
    db = Database()
    make_user(db, 1)
    make_user(db, 2)
    db.create_request(1, 2)
    assert db.cancel_request(1, 2) is True
    assert db.request_status(1, 2) is None


# ── Verification ────────────────────────────────────────────────

def test_verification_queue_and_approval():
    db = Database()
    user = make_user(db, 1)
    assert db.queue_verification(1, Gender.FEMALE, "ev_1") is True
    assert db.pending_verifications_list() == [(1, db.pending_verifications[1])]

    approved = db.approve_verification(1)
    assert approved is user
    assert user.verified is True
    assert user.verified_gender == Gender.FEMALE
    assert db.pending_verifications_list() == []
    assert db.approve_verification(1) is None            # nothing pending


def test_verification_reject_allows_retry():
    db = Database()
    user = make_user(db, 1)
    db.queue_verification(1, Gender.MALE, "ev_1")
    assert db.reject_verification(1) is True
    assert db.reject_verification(1) is False
    assert user.verified is False
    assert db.queue_verification(1, Gender.MALE, "ev_2") is True


def test_verified_user_cannot_queue_again():
    db = Database()
    make_user(db, 1)
    db.queue_verification(1, Gender.MALE, "ev_1")
    db.approve_verification(1)
    assert db.queue_verification(1, Gender.MALE, "ev_2") is False
