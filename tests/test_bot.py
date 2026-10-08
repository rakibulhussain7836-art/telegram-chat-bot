"""Tests for bot.py: helpers, search/coin logic, payments, referrals and reports."""

import asyncio
from types import SimpleNamespace

import bot
from database import (
    BAN_REPORT_THRESHOLD,
    ChatState,
    Gender,
    GIRL_SEARCH_COST,
    CHAT_REQUEST_COST,
    STARTING_COINS,
)


# ── Fakes ────────────────────────────────────────────────────────

def run(coro):
    return asyncio.run(coro)


class FakeUser:
    def __init__(self, user_id, username=None):
        self.id = user_id
        self.username = username


class FakeMessage:
    def __init__(self, text=None, photo=None, caption=None, location=None):
        self.replies = []
        self.text = text
        self.photo = photo
        self.caption = caption
        self.location = location

    async def reply_text(self, text, **kwargs):
        self.replies.append({"text": text, **kwargs})


class FakeUpdate:
    def __init__(self, user_id, username=None, message=None, callback_query=None):
        self.effective_user = FakeUser(user_id, username)
        self.message = message or FakeMessage()
        self.callback_query = callback_query
        self.args = []


class FakeQuery:
    def __init__(self, user_id, data):
        self.data = data
        self.from_user = FakeUser(user_id)
        self.edits = []
        self.answers = []

    async def answer(self, text=None, show_alert=False):
        self.answers.append({"text": text, "show_alert": show_alert})

    async def edit_message_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(
            {"text": text, "parse_mode": parse_mode, "reply_markup": reply_markup}
        )


class FakeBot:
    def __init__(self):
        self.sent = []
        self.photos = []

    async def send_message(self, chat_id=None, text=None, **kwargs):
        self.sent.append({"chat_id": chat_id, "text": text, **kwargs})

    async def send_photo(self, chat_id=None, photo=None, caption=None, **kwargs):
        self.photos.append({"chat_id": chat_id, "photo": photo, "caption": caption})


class FakeContext:
    def __init__(self):
        self.bot = FakeBot()
        self.args = []
        self.user_data = {}


class FakeInvoiceQuery:
    def __init__(self, payload):
        self.invoice_payload = payload
        self.answers = []

    async def answer(self, ok, error_message=None):
        self.answers.append({"ok": ok, "error_message": error_message})


class FakePayment:
    def __init__(self, payload, charge_id="ch_1"):
        self.invoice_payload = payload
        self.telegram_payment_charge_id = charge_id


def register(db, uid, gender=Gender.MALE, country="US"):
    user = db.register_user(uid)
    db.update_gender(uid, gender)
    db.update_country(uid, country)
    return user


# ── Helpers / templates ─────────────────────────────────────────

def test_format_gender_and_state():
    assert bot.format_gender(Gender.MALE).startswith("👨")
    assert bot.format_gender(Gender.FEMALE).startswith("👩")
    assert bot.format_gender(None) == "Not set"
    assert bot.format_state(ChatState.CHATTING) == "💬 In Chat"
    assert bot.format_state(None) == "Unknown"


def test_help_text_has_search_cost_filled_in():
    text = bot.HELP_MSG.format(cost=GIRL_SEARCH_COST, request_cost=CHAT_REQUEST_COST)
    assert str(GIRL_SEARCH_COST) in text
    assert str(CHAT_REQUEST_COST) in text
    assert "{cost}" not in text
    assert "{request_cost}" not in text


def test_credit_text_shows_balance_and_earn_options(fresh_db):
    user = fresh_db.register_user(1)
    text = bot.credit_text(user)
    assert f"**{STARTING_COINS}**" in text
    assert "/link" in text


def test_build_profile_text_shows_coins_likes_referrals(fresh_db):
    user = register(fresh_db, 1)
    fresh_db.add_like(2, 1)
    text = bot.build_profile_text(user)
    assert f"🪙 {STARTING_COINS}" in text
    assert "❤️ 1" in text
    assert "US" in text


# ── Search & coins ──────────────────────────────────────────────

def test_random_search_is_free(fresh_db):
    register(fresh_db, 1)
    text, markup, mode = asyncio.run(bot.begin_search(FakeContext(), 1, Gender.ANY))
    assert fresh_db.get_user(1).coins == STARTING_COINS
    assert fresh_db.get_user(1).state == ChatState.SEARCHING
    assert "Searching" in text


def test_girl_search_charges_coins(fresh_db):
    register(fresh_db, 1)
    text, _, mode = asyncio.run(bot.begin_search(FakeContext(), 1, Gender.FEMALE))
    assert fresh_db.get_user(1).coins == STARTING_COINS - GIRL_SEARCH_COST
    assert f"-{GIRL_SEARCH_COST}" in text
    assert mode == "Markdown"
    assert fresh_db.get_user(1).search_pref == Gender.FEMALE


def test_girl_search_without_coins_is_refused(fresh_db):
    user = register(fresh_db, 1)
    user.coins = 0
    text, markup, mode = asyncio.run(bot.begin_search(FakeContext(), 1, Gender.FEMALE))
    assert "Not enough Coins" in text
    assert markup is not None
    assert fresh_db.get_user(1).state == ChatState.IDLE
    assert fresh_db.get_user(1).coins == 0


def test_cancelled_search_keeps_the_charge(fresh_db):
    register(fresh_db, 1)
    asyncio.run(bot.begin_search(FakeContext(), 1, Gender.FEMALE))
    fresh_db.remove_from_queue(1)
    assert fresh_db.get_user(1).coins == STARTING_COINS - GIRL_SEARCH_COST


def test_search_requires_complete_profile(fresh_db):
    fresh_db.register_user(1)
    text, markup, mode = asyncio.run(bot.begin_search(FakeContext(), 1, Gender.ANY))
    assert "complete your profile" in text
    assert fresh_db.get_user(1).state == ChatState.IDLE


def test_banned_user_cannot_search(fresh_db):
    user = register(fresh_db, 1)
    user.banned = True
    text, markup, mode = asyncio.run(bot.begin_search(FakeContext(), 1, Gender.ANY))
    assert "restricted" in text
    assert fresh_db.searching_count == 0


def test_already_searching_is_reported(fresh_db):
    register(fresh_db, 1)
    asyncio.run(bot.begin_search(FakeContext(), 1, Gender.ANY))
    text, markup, mode = asyncio.run(bot.begin_search(FakeContext(), 1, Gender.ANY))
    assert "already searching" in text


def test_unknown_user_gets_start_prompt(fresh_db):
    text, _, _ = asyncio.run(bot.begin_search(FakeContext(), 404, Gender.ANY))
    assert "/start" in text


def test_pairing_after_girl_search_notifies_partner(fresh_db):
    register(fresh_db, 1, gender=Gender.MALE, country="US")
    register(fresh_db, 2, gender=Gender.FEMALE, country="FR")
    fresh_db.add_to_queue(2, search_pref=None)
    ctx = FakeContext()

    text, _, _ = asyncio.run(bot.begin_search(ctx, 1, Gender.FEMALE))

    assert "Partner found" in text
    assert fresh_db.get_user(1).state == ChatState.CHATTING
    assert len(ctx.bot.sent) == 2


# ── Payments (Telegram Stars) ───────────────────────────────────

def test_valid_pre_checkout_is_approved(fresh_db):
    fresh_db.register_user(1)
    query = FakeInvoiceQuery("coin_pack:1:280")
    update = type("U", (), {"pre_checkout_query": query})()
    asyncio.run(bot.pre_checkout_handler(update, FakeContext()))
    assert query.answers[0]["ok"] is True


def test_pre_checkout_rejects_bad_payload(fresh_db):
    fresh_db.register_user(1)
    for payload in ("", "coin_pack:x:280", "coin_pack:1:0", "coin_pack:404:280"):
        query = FakeInvoiceQuery(payload)
        update = type("U", (), {"pre_checkout_query": query})()
        asyncio.run(bot.pre_checkout_handler(update, FakeContext()))
        assert query.answers[0]["ok"] is False, payload
        assert query.answers[0]["error_message"]


def test_payment_awards_coins(fresh_db):
    fresh_db.register_user(1)
    update = FakeUpdate(1)
    update.message.successful_payment = FakePayment("coin_pack:1:280")

    asyncio.run(bot.payment_success_handler(update, FakeContext()))

    assert fresh_db.get_user(1).coins == STARTING_COINS + 280
    assert "Payment successful" in update.message.replies[0]["text"]


def test_duplicate_charge_id_is_ignored(fresh_db):
    fresh_db.register_user(1)
    for _ in range(2):
        update = FakeUpdate(1)
        update.message.successful_payment = FakePayment("coin_pack:1:280", "ch_same")
        asyncio.run(bot.payment_success_handler(update, FakeContext()))

    assert fresh_db.get_user(1).coins == STARTING_COINS + 280
    assert len(fresh_db.processed_charges) == 1


def test_unverifiable_payment_is_not_credited(fresh_db):
    update = FakeUpdate(1)
    update.message.successful_payment = FakePayment("coin_pack:404:280")
    asyncio.run(bot.payment_success_handler(update, FakeContext()))
    assert "could not be verified" in update.message.replies[0]["text"]


# ── Referral deep link ──────────────────────────────────────────

def test_start_with_referral_code_credits_both(fresh_db):
    register(fresh_db, 1)
    update = FakeUpdate(2, "newbie")
    context = FakeContext()
    context.args = [str(1)]

    asyncio.run(bot.start_command(update, context))

    assert fresh_db.get_user(1).coins > STARTING_COINS
    assert fresh_db.get_user(2).coins > STARTING_COINS
    assert fresh_db.get_user(2).referred_by == 1
    assert "Referral bonus" in update.message.replies[0]["text"]


def test_start_without_referral_keeps_balance(fresh_db):
    update = FakeUpdate(2, "newbie")
    asyncio.run(bot.start_command(update, FakeContext()))
    assert fresh_db.get_user(2).coins == STARTING_COINS
    assert fresh_db.get_user(2).referred_by is None


def test_start_ends_an_active_chat(fresh_db):
    register(fresh_db, 1)
    register(fresh_db, 2, gender=Gender.FEMALE)
    fresh_db.add_to_queue(1)
    fresh_db.add_to_queue(2)
    fresh_db.pair_users(1, 2)

    ctx = FakeContext()
    asyncio.run(bot.start_command(FakeUpdate(1), ctx))

    assert fresh_db.get_user(1).state == ChatState.IDLE
    assert fresh_db.get_user(2).state == ChatState.IDLE
    assert any("partner has left" in m["text"] for m in ctx.bot.sent)


# ── Reports ─────────────────────────────────────────────────────

def test_report_ends_chat_and_bans_at_threshold(fresh_db):
    target = 150
    register(fresh_db, target, gender=Gender.FEMALE)

    for i in range(BAN_REPORT_THRESHOLD):
        reporter = 100 + i
        register(fresh_db, reporter)
        fresh_db.add_to_queue(reporter)
        fresh_db.add_to_queue(target)
        fresh_db.pair_users(reporter, target)

        ctx = FakeContext()
        message, was_in_chat = asyncio.run(bot.process_report(ctx, reporter))
        assert was_in_chat is True
        assert "Report submitted" in message

    assert fresh_db.get_user(target).banned is True
    assert fresh_db.chatting_count == 0


def test_report_without_chat_is_rejected(fresh_db):
    register(fresh_db, 1)
    message, was_in_chat = asyncio.run(bot.process_report(FakeContext(), 1))
    assert was_in_chat is False
    assert "no active chat" in message


# ── Profile photo ───────────────────────────────────────────────

def test_photo_upload_is_saved(fresh_db):
    register(fresh_db, 1)
    ctx = FakeContext()
    ctx.user_data["awaiting_photo"] = True
    update = FakeUpdate(1, message=FakeMessage(photo=[SimpleNamespace(file_id="photo_1")]))

    asyncio.run(bot.relay_message(update, ctx))

    assert fresh_db.get_user(1).photo_file_id == "photo_1"
    assert ctx.user_data["awaiting_photo"] is False
    assert "saved" in update.message.replies[0]["text"]


def test_non_photo_cancels_photo_setting(fresh_db):
    register(fresh_db, 1)
    ctx = FakeContext()
    ctx.user_data["awaiting_photo"] = True
    update = FakeUpdate(1, message=FakeMessage(text="hello"))

    asyncio.run(bot.relay_message(update, ctx))

    assert fresh_db.get_user(1).photo_file_id is None
    assert ctx.user_data["awaiting_photo"] is False
    assert "cancelled" in update.message.replies[0]["text"]


def test_photo_is_not_relayed_to_partner_while_setting(fresh_db):
    register(fresh_db, 1)
    register(fresh_db, 2, gender=Gender.FEMALE)
    fresh_db.add_to_queue(1)
    fresh_db.add_to_queue(2)
    fresh_db.pair_users(1, 2)

    ctx = FakeContext()
    ctx.user_data["awaiting_photo"] = True
    update = FakeUpdate(1, message=FakeMessage(photo=[SimpleNamespace(file_id="photo_1")]))

    asyncio.run(bot.relay_message(update, ctx))

    assert ctx.bot.photos == []          # not sent to the partner
    assert fresh_db.get_user(1).photo_file_id == "photo_1"


def test_partner_receives_my_photo_on_match(fresh_db):
    register(fresh_db, 1, gender=Gender.MALE, country="US")
    register(fresh_db, 2, gender=Gender.FEMALE, country="FR")
    fresh_db.set_photo(1, "photo_of_1")
    fresh_db.add_to_queue(1)

    ctx = FakeContext()
    text, _, _ = asyncio.run(bot.begin_search(ctx, 2, Gender.ANY))

    assert "Partner found" in text
    assert any(
        p["chat_id"] == 2 and p["photo"] == "photo_of_1" for p in ctx.bot.photos
    )
    assert not any(p["chat_id"] == 1 for p in ctx.bot.photos)  # no own photo back


def test_match_without_photos_sends_none(fresh_db):
    register(fresh_db, 1, gender=Gender.MALE, country="US")
    register(fresh_db, 2, gender=Gender.FEMALE, country="FR")
    fresh_db.add_to_queue(1)

    ctx = FakeContext()
    asyncio.run(bot.begin_search(ctx, 2, Gender.ANY))

    assert ctx.bot.photos == []


# ── Helper: press an inline button ──────────────────────────────

def press(user_id, data, context=None):
    query = FakeQuery(user_id, data)
    update = FakeUpdate(user_id, callback_query=query)
    context = context or FakeContext()
    asyncio.run(bot.button_handler(update, context))
    return query, context


def _buttons(markup):
    return [b for row in markup.inline_keyboard for b in row]


# ── Public ID / profile card ────────────────────────────────────

def test_profile_shows_public_id_contacts_and_verification(fresh_db):
    user = register(fresh_db, 1)
    text = bot.build_profile_text(user)
    assert f"`{user.public_id}`" in text
    assert "📇" in text and "❌ Not verified" in text


def test_find_id_prompts_for_input(fresh_db):
    register(fresh_db, 1)
    query, context = press(1, "find_id")
    assert context.user_data["awaiting_id"] is True
    assert "Find by ID" in query.edits[-1]["text"]


def test_id_search_shows_profile_card(fresh_db):
    register(fresh_db, 1)
    target = register(fresh_db, 2, gender=Gender.FEMALE)
    context = FakeContext()
    context.user_data["awaiting_id"] = True
    update = FakeUpdate(1, message=FakeMessage(text=str(target.public_id)))

    asyncio.run(bot.relay_message(update, context))

    reply = update.message.replies[0]
    assert f"`{target.public_id}`" in reply["text"]
    labels = [b.text for b in _buttons(reply["reply_markup"])]
    assert any("Like" in label for label in labels)
    assert any(f"{CHAT_REQUEST_COST}" in label for label in labels)


def test_id_search_with_unknown_id(fresh_db):
    register(fresh_db, 1)
    context = FakeContext()
    context.user_data["awaiting_id"] = True
    update = FakeUpdate(1, message=FakeMessage(text="999999"))

    asyncio.run(bot.relay_message(update, context))

    assert "No account found" in update.message.replies[0]["text"]


def test_own_public_id_is_six_digits(fresh_db):
    user = register(fresh_db, 1)
    assert 100000 <= user.public_id <= 999999


# ── Nearby ──────────────────────────────────────────────────────

def test_nearby_prompts_for_location_when_missing(fresh_db):
    register(fresh_db, 1)
    query, context = press(1, "nearby")
    assert "location" in query.edits[-1]["text"].lower()
    assert context.user_data["awaiting_location"] is True


def test_location_share_saves_and_lists_nearby(fresh_db):
    register(fresh_db, 1)
    near = register(fresh_db, 2, gender=Gender.FEMALE)
    fresh_db.set_location(2, 10.0, 20.0)

    context = FakeContext()
    context.user_data["awaiting_location"] = True
    message = FakeMessage(location=SimpleNamespace(latitude=10.0, longitude=20.05))
    update = FakeUpdate(1, message=message)

    asyncio.run(bot.relay_message(update, context))

    assert fresh_db.has_location(1)
    reply = update.message.replies[0]
    assert "Location saved" in reply["text"]
    callback_datas = [b.callback_data for b in _buttons(reply["reply_markup"])]
    assert f"view_{near.user_id}" in callback_datas


def test_nearby_list_shows_distance(fresh_db):
    register(fresh_db, 1)
    fresh_db.set_location(1, 10.0, 20.0)
    other = register(fresh_db, 2)
    fresh_db.set_location(2, 10.0, 20.1)

    query, _ = press(1, "nearby")

    assert f"view_{other.user_id}" in [
        b.callback_data for b in _buttons(query.edits[-1]["reply_markup"])
    ]
    assert "People near you" in query.edits[-1]["text"]


def test_non_location_message_cancels_location_flow(fresh_db):
    register(fresh_db, 1)
    context = FakeContext()
    context.user_data["awaiting_location"] = True
    update = FakeUpdate(1, message=FakeMessage(text="hello"))

    asyncio.run(bot.relay_message(update, context))

    assert not fresh_db.has_location(1)
    assert "wasn't a location" in update.message.replies[0]["text"]


# ── Like / unlike ───────────────────────────────────────────────

def test_like_toggle_from_profile_card(fresh_db):
    register(fresh_db, 1)
    register(fresh_db, 2)

    query, _ = press(1, f"like_toggle_{2}")
    assert fresh_db.get_user(2).likes == 1
    assert query.answers[-1]["text"] == "❤️ Liked!"
    assert "Unlike" in [
        b.text for b in _buttons(query.edits[-1]["reply_markup"])
    ][0]

    query, _ = press(1, f"like_toggle_{2}")
    assert fresh_db.get_user(2).likes == 0
    assert query.answers[-1]["text"] == "💔 Like removed"


def test_cannot_like_your_own_profile(fresh_db):
    register(fresh_db, 1)

    query, _ = press(1, f"like_toggle_{1}")

    assert fresh_db.get_user(1).likes == 0
    assert query.answers[-1]["text"] == "You can't like this profile."


# ── Chat requests ───────────────────────────────────────────────

def test_chat_request_charges_coins_and_delivers(fresh_db):
    register(fresh_db, 1)
    register(fresh_db, 2)
    before = fresh_db.get_user(1).coins

    query, context = press(1, f"req_chat_{2}")

    assert fresh_db.get_user(1).coins == before - CHAT_REQUEST_COST
    assert fresh_db.request_status(1, 2) == "pending"
    assert query.answers[-1]["text"] == "📨 Request sent!"
    delivered = [m for m in context.bot.sent if m["chat_id"] == 2]
    assert delivered and delivered[0]["reply_markup"] is not None


def test_chat_request_without_coins_is_refused(fresh_db):
    sender = register(fresh_db, 1)
    register(fresh_db, 2)
    sender.coins = 0

    query, _ = press(1, f"req_chat_{2}")

    assert fresh_db.request_status(1, 2) is None
    assert query.answers[-1]["show_alert"] is True


def test_duplicate_chat_request_is_refused(fresh_db):
    register(fresh_db, 1)
    register(fresh_db, 2)
    fresh_db.create_request(1, 2)
    balance = fresh_db.get_user(1).coins

    query, _ = press(1, f"req_chat_{2}")

    assert fresh_db.request_status(1, 2) == "pending"
    assert fresh_db.get_user(1).coins == balance  # charged only once


def test_accepting_request_pairs_both_users(fresh_db):
    register(fresh_db, 1)
    register(fresh_db, 2)
    fresh_db.create_request(1, 2)

    query, _ = press(2, "req_yes_1")

    assert fresh_db.get_user(1).state == ChatState.CHATTING
    assert fresh_db.get_user(2).state == ChatState.CHATTING
    assert fresh_db.get_user(1).partner_id == 2
    assert "accepted" in query.edits[-1]["text"].lower()


def test_declining_request_notifies_requester(fresh_db):
    register(fresh_db, 1)
    register(fresh_db, 2)
    fresh_db.create_request(1, 2)

    query, context = press(2, "req_no_1")

    assert fresh_db.request_status(1, 2) == "declined"
    assert "declined" in query.edits[-1]["text"].lower()
    assert any(
        m["chat_id"] == 1 and "declined" in m["text"].lower()
        for m in context.bot.sent
    )


def test_accept_fails_when_target_busy_and_keeps_request(fresh_db):
    register(fresh_db, 1)
    register(fresh_db, 2)
    register(fresh_db, 3, gender=Gender.FEMALE)
    fresh_db.add_to_queue(2)
    fresh_db.add_to_queue(3)
    fresh_db.pair_users(2, 3)          # acceptor is already chatting
    fresh_db.create_request(1, 2)

    query, _ = press(2, "req_yes_1")

    assert "already in a chat" in query.answers[-1]["text"]
    assert fresh_db.request_status(1, 2) == "pending"   # not burned
    assert fresh_db.get_user(1).state == ChatState.IDLE


def test_accept_is_refused_for_banned_accounts(fresh_db):
    requester = register(fresh_db, 1)
    register(fresh_db, 2)
    fresh_db.create_request(1, 2)
    requester.banned = True

    query, _ = press(2, "req_yes_1")

    assert "restricted" in query.answers[-1]["text"].lower()
    assert fresh_db.request_status(1, 2) == "pending"
    assert fresh_db.get_user(2).state == ChatState.IDLE


def test_back_list_returns_to_previous_list(fresh_db):
    register(fresh_db, 1)
    other = register(fresh_db, 2)
    fresh_db.add_contact(1, 2)

    context = FakeContext()
    press(1, "contacts", context)
    press(1, f"view_{2}", context)
    query, _ = press(1, "back_list", context)

    assert f"view_{other.user_id}" in [
        b.callback_data for b in _buttons(query.edits[-1]["reply_markup"])
    ]


# ── Contacts ────────────────────────────────────────────────────

def test_add_contact_requires_active_chat(fresh_db):
    register(fresh_db, 1)
    query, _ = press(1, "add_contact")
    assert query.answers[-1]["show_alert"] is True
    assert fresh_db.contacts_of(1) == []


def test_add_contact_while_chatting(fresh_db):
    register(fresh_db, 1)
    register(fresh_db, 2, gender=Gender.FEMALE)
    fresh_db.add_to_queue(1)
    fresh_db.add_to_queue(2)
    fresh_db.pair_users(1, 2)

    query, _ = press(1, "add_contact")

    assert [u.user_id for u in fresh_db.contacts_of(1)] == [2]
    assert "Added" in query.answers[-1]["text"]

    query, _ = press(1, "add_contact")   # second tap
    assert query.answers[-1]["text"] == "Already in your contacts."


def test_contacts_list_button(fresh_db):
    register(fresh_db, 1)
    other = register(fresh_db, 2)
    fresh_db.add_contact(1, 2)

    query, _ = press(1, "contacts")

    assert f"view_{other.user_id}" in [
        b.callback_data for b in _buttons(query.edits[-1]["reply_markup"])
    ]


def test_empty_contacts_shows_hint(fresh_db):
    register(fresh_db, 1)
    query, _ = press(1, "contacts")
    assert "No contacts yet" in query.edits[-1]["text"]


# ── Verification ────────────────────────────────────────────────

def test_verification_flow_queues_photo_evidence(fresh_db):
    register(fresh_db, 1)

    query, context = press(1, "verify_boy")
    assert context.user_data["awaiting_verify"] is True
    assert context.user_data["verify_gender"] == Gender.MALE

    update = FakeUpdate(
        1, message=FakeMessage(photo=[SimpleNamespace(file_id="evidence_1")])
    )
    asyncio.run(bot.relay_message(update, context))

    assert 1 in fresh_db.pending_verifications
    assert fresh_db.pending_verifications[1]["file_id"] == "evidence_1"
    assert "submitted" in update.message.replies[0]["text"]


def test_admin_can_approve_verification(fresh_db, monkeypatch):
    register(fresh_db, 1)
    fresh_db.queue_verification(1, Gender.MALE, "evidence_1")
    monkeypatch.setattr(bot, "ADMIN_ID", 999)

    update = FakeUpdate(999)
    context = FakeContext()
    context.args = [str(fresh_db.get_user(1).public_id)]
    asyncio.run(bot.verifyok_command(update, context))

    user = fresh_db.get_user(1)
    assert user.verified is True
    assert user.verified_gender == Gender.MALE
    assert "✅ Verified" in update.message.replies[0]["text"]
    assert any(m["chat_id"] == 1 for m in context.bot.sent)


def test_non_admin_cannot_verify(fresh_db, monkeypatch):
    register(fresh_db, 1)
    fresh_db.queue_verification(1, Gender.MALE, "evidence_1")
    monkeypatch.setattr(bot, "ADMIN_ID", 999)

    update = FakeUpdate(1)
    context = FakeContext()
    context.args = ["1"]
    asyncio.run(bot.verifyok_command(update, context))

    assert fresh_db.get_user(1).verified is False
    assert 1 in fresh_db.pending_verifications
    assert update.message.replies == []


def test_verify_without_admin_id_is_disabled(fresh_db, monkeypatch):
    register(fresh_db, 1)
    fresh_db.queue_verification(1, Gender.MALE, "evidence_1")
    monkeypatch.setattr(bot, "ADMIN_ID", None)

    update = FakeUpdate(1)
    context = FakeContext()
    context.args = ["1"]
    asyncio.run(bot.verifyok_command(update, context))

    assert fresh_db.get_user(1).verified is False
    assert update.message.replies == []


def test_verified_label_shows_gender(fresh_db):
    user = register(fresh_db, 1)
    user.verified = True
    user.verified_gender = Gender.FEMALE
    assert bot.verified_label(user) == "✅ Verified Girl"
