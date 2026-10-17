"""Tests for bot.py: helpers, search/coin logic, payments, referrals and reports."""

import asyncio
from types import SimpleNamespace

import bot
from database import (
    BAN_REPORT_THRESHOLD,
    ChatState,
    Gender,
    GIRL_SEARCH_COST,
    GUY_SEARCH_COST,
    CHAT_REQUEST_COST,
    DIRECT_MESSAGE_COST,
    NOTIFY_COST,
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
        # like real Telegram updates: a callback query arrives without a message
        self.message = message or (FakeMessage() if callback_query is None else None)
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
        self.member_status = "member"   # force-join gate: "left" = not joined

    async def get_chat_member(self, chat_id, user_id):
        return SimpleNamespace(status=self.member_status)

    async def send_message(self, chat_id=None, text=None, **kwargs):
        self.sent.append({"chat_id": chat_id, "text": text, **kwargs})

    async def send_photo(self, chat_id=None, photo=None, caption=None, **kwargs):
        self.photos.append({
            "chat_id": chat_id,
            "photo": photo,
            "caption": caption,
            "reply_markup": kwargs.get("reply_markup"),
        })


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


def register(db, uid, gender=Gender.MALE, country="US", complete=True):
    """Registered user. `complete=True` also fills the mandatory
    name/age/city fields (what onboarding collects)."""
    user = db.register_user(uid, name=f"User{uid}" if complete else None)
    db.update_gender(uid, gender)
    db.update_country(uid, country)
    if complete:
        db.update_age(uid, 25)
        db.update_city(uid, "Springfield")
    return user


# ── Helpers / templates ─────────────────────────────────────────

def test_format_gender_and_state():
    assert bot.format_gender(Gender.MALE).startswith("👨")
    assert bot.format_gender(Gender.FEMALE).startswith("👩")
    assert bot.format_gender(None) == "Not set"
    assert bot.format_state(ChatState.CHATTING) == "💬 In Chat"
    assert bot.format_state(None) == "Unknown"


def test_help_text_has_search_cost_filled_in():
    text = bot.HELP_MSG.format(**bot.HELP_KWARGS)
    assert str(GIRL_SEARCH_COST) in text
    assert str(CHAT_REQUEST_COST) in text
    assert str(DIRECT_MESSAGE_COST) in text
    assert str(bot.HELP_KWARGS["notify_cost"]) in text
    assert str(STARTING_COINS) in text
    for placeholder in (
        "{cost}", "{request_cost}", "{dm_cost}", "{notify_cost}", "{free}"
    ):
        assert placeholder not in text


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


def test_guy_search_charges_coins(fresh_db):
    register(fresh_db, 1)
    text, _, mode = asyncio.run(bot.begin_search(FakeContext(), 1, Gender.MALE))
    assert fresh_db.get_user(1).coins == STARTING_COINS - GUY_SEARCH_COST
    assert f"-{GUY_SEARCH_COST}" in text
    assert mode == "Markdown"
    assert fresh_db.get_user(1).search_pref == Gender.MALE


def test_guy_search_without_coins_is_refused(fresh_db):
    user = register(fresh_db, 1)
    user.coins = 1  # one short of a 2-coin search
    text, markup, mode = asyncio.run(bot.begin_search(FakeContext(), 1, Gender.MALE))
    assert "Not enough Coins" in text
    assert markup is not None
    assert fresh_db.get_user(1).state == ChatState.IDLE
    assert user.coins == 1


def test_new_users_start_with_4_tokens(fresh_db):
    user = fresh_db.register_user(42)
    assert user.coins == 4
    assert STARTING_COINS == 4


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
    # ONE card per user: the partner's photo carries the info + buttons
    assert len(ctx.bot.photos) == 2
    for card in ctx.bot.photos:
        assert "Partner found" in card["caption"]
        assert card["reply_markup"] is not None
    assert ctx.bot.sent == []  # never a separate text message underneath


# ── Continuous "matching" animation ──────────────────────────────

def _recording_target(edits, markups):
    class Target:
        async def edit_message_text(self, text, parse_mode=None, reply_markup=None):
            edits.append(text)
            markups.append(reply_markup)

    return Target()


def test_matching_animation_runs_until_a_match_lands(fresh_db, monkeypatch):
    """The frames must keep cycling (past one full cycle) until a match."""
    import animations

    monkeypatch.setattr(animations, "ANIMATIONS_ENABLED", True)
    register(fresh_db, 1, gender=Gender.MALE, country="US")
    register(fresh_db, 2, gender=Gender.FEMALE, country="FR")
    edits, markups = [], []
    calls = {"n": 0}

    def check():
        calls["n"] += 1
        if calls["n"] >= 8:  # longer than one 6-frame cycle
            fresh_db.pair_users(1, 2)
            return 2
        return None

    found = asyncio.run(
        bot.animate_search(
            FakeContext(), 1, check,
            target=_recording_target(edits, markups),
            interval=0,
            reply_markup=bot.searching_keyboard(),
        )
    )

    assert found == 2
    assert len(edits) > 6  # kept animating past the first 6-frame cycle
    assert "Matching you with a partner" in edits[0]
    assert "Matching you with a partner" in edits[-1]
    # the Cancel Search button stays reachable on every frame
    assert all(
        any(b.callback_data == "cancel_search" for b in _buttons(markup))
        for markup in markups
    )
    assert fresh_db.get_user(1).state == ChatState.CHATTING


def test_matching_animation_stops_when_the_search_is_cancelled(fresh_db, monkeypatch):
    import animations

    monkeypatch.setattr(animations, "ANIMATIONS_ENABLED", True)
    register(fresh_db, 1)
    fresh_db.add_to_queue(1, search_pref=None)
    edits, markups = [], []
    calls = {"n": 0}

    def check():
        calls["n"] += 1
        if calls["n"] == 3:
            fresh_db.remove_from_queue(1)  # the user pressed Cancel Search
        return None

    def cancelled():
        me = fresh_db.get_user(1)
        return me is None or me.state != ChatState.SEARCHING

    found = asyncio.run(
        bot.animate_search(
            FakeContext(), 1, check,
            target=_recording_target(edits, markups),
            interval=0,
            stop_check=cancelled,
        )
    )

    assert found is None
    assert len(edits) == 2  # no frame is drawn after the cancel
    assert fresh_db.get_user(1).state == ChatState.IDLE


def test_animated_search_rewrites_the_frame_when_the_user_cancels(
    fresh_db, monkeypatch
):
    """After Cancel the on-screen frame must not keep saying 'matching...'."""
    register(fresh_db, 1)
    edits, markups = [], []

    async def fake_search(context, user_id, check, **kwargs):
        fresh_db.remove_from_queue(user_id)  # Cancel pressed mid-animation
        return None

    monkeypatch.setattr(bot, "ANIMATIONS_ENABLED", True)
    monkeypatch.setattr(bot, "animate_search", fake_search)

    text, markup, mode = asyncio.run(
        bot.begin_search(
            FakeContext(), 1, Gender.FEMALE, target=_recording_target(edits, markups)
        )
    )

    assert (text, markup, mode) == (None, None, None)
    assert len(edits) == 1
    assert "Search cancelled." in edits[0]
    assert "-2" in edits[0]  # the Girl-search charge is still shown
    assert any(
        b.callback_data == "find_partner" for b in _buttons(markups[-1])
    )


# ── Photo/caption card animation helpers ────────────────────────

class _FakeCaptionMsg:
    def __init__(self, fail_first_edit=False):
        self.captions = []
        self.marks = []
        self._attempts = 0
        self._fail_first = fail_first_edit

    async def edit_caption(self, caption=None, parse_mode=None, reply_markup=None):
        self._attempts += 1
        if self._fail_first and self._attempts == 1:
            raise RuntimeError("flood control: retry later")
        self.captions.append(caption)
        self.marks.append(reply_markup)


def test_caption_animation_types_through_every_frame(monkeypatch):
    import animations

    monkeypatch.setattr(animations, "ANIMATIONS_ENABLED", True)
    markup = bot.main_menu_keyboard()
    msg = _FakeCaptionMsg()

    ok = asyncio.run(
        animations.animate_message_caption(
            msg, ["c1", "c2", "c3"], reply_markup=markup, interval=0
        )
    )

    assert ok is True
    assert msg.captions == ["c1", "c2", "c3"]
    # buttons only ride in with the finished frame
    assert msg.marks[:-1] == [None, None]
    assert msg.marks[-1] is markup


def test_caption_animation_falls_back_to_the_finished_card(monkeypatch):
    import animations

    monkeypatch.setattr(animations, "ANIMATIONS_ENABLED", True)
    markup = bot.main_menu_keyboard()
    msg = _FakeCaptionMsg(fail_first_edit=True)

    ok = asyncio.run(
        animations.animate_message_caption(
            msg, ["c1", "c2", "c3"], reply_markup=markup, interval=0
        )
    )

    assert ok is True  # the finished card still landed
    assert msg.captions == ["c3"]
    assert msg.marks[-1] is markup


def test_caption_animation_reports_an_uneditable_message():
    import animations

    frames = ["c1", "c2"]
    assert (
        asyncio.run(animations.animate_message_caption(object(), frames)) is False
    )


def test_photo_card_sends_one_message_and_adds_buttons_at_the_end(monkeypatch):
    import animations

    monkeypatch.setattr(animations, "ANIMATIONS_ENABLED", True)
    markup = bot.main_menu_keyboard()

    class RecordingBot:
        def __init__(self):
            self.sent = None
            self.msg = _FakeCaptionMsg()

        async def send_photo(self, **kwargs):
            self.sent = kwargs
            return self.msg

    recording = RecordingBot()
    ok = asyncio.run(
        animations.animate_photo_card(
            recording, 1, "photo-id", ["f1", "f2"],
            reply_markup=markup, interval=0,
        )
    )

    assert ok is True
    assert recording.sent["caption"] == "f1"  # first frame opens the card
    assert recording.sent.get("reply_markup") is None
    assert recording.msg.captions == ["f2"]
    assert recording.msg.marks[-1] is markup  # buttons arrive on ONE message


def test_photo_card_returns_false_when_the_photo_cannot_be_sent(monkeypatch):
    import animations

    class BrokenBot:
        async def send_photo(self, **kwargs):
            raise RuntimeError("chat not found")

    assert (
        asyncio.run(
            animations.animate_photo_card(
                BrokenBot(), 1, "photo-id", ["f1"], interval=0
            )
        )
        is False
    )


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
    # user 1 gets the partner's default photo back (never their own photo)
    to_1 = [p for p in ctx.bot.photos if p["chat_id"] == 1]
    assert all(p["photo"] != "photo_of_1" for p in to_1)
    assert any(
        hasattr(p["photo"], "name") and "default_girl" in p["photo"].name
        for p in to_1
    )


def test_match_without_photos_sends_ai_avatar(fresh_db):
    register(fresh_db, 1, gender=Gender.MALE, country="US")
    register(fresh_db, 2, gender=Gender.FEMALE, country="FR")
    fresh_db.add_to_queue(1)

    ctx = FakeContext()
    asyncio.run(bot.begin_search(ctx, 2, Gender.ANY))

    # No photo was set → the partner still gets a default photo card
    avatar_photos = [
        p for p in ctx.bot.photos
        if hasattr(p["photo"], "name")
    ]
    assert len(avatar_photos) >= 1
    # user 1 (boy) sees the girl's photo, user 2 (girl) the boy's
    to_2 = next(p for p in avatar_photos if p["chat_id"] == 2)
    assert "default_boy" in to_2["photo"].name
    to_1 = next(p for p in avatar_photos if p["chat_id"] == 1)
    assert "default_girl" in to_1["photo"].name
    assert not any(p["chat_id"] == 1 and p["photo"] == "photo_of_1" for p in ctx.bot.photos)


def test_default_photo_is_gendered(fresh_db):
    boy = register(fresh_db, 1, gender=Gender.MALE)
    girl = register(fresh_db, 2, gender=Gender.FEMALE)
    assert bot.default_photo_path(boy).endswith("default_boy.jpg")
    assert bot.default_photo_path(girl).endswith("default_girl.png")
    # a real photo always wins over the default
    fresh_db.set_photo(1, "real_photo")
    assert bot.profile_photo_of(fresh_db.get_user(1)) == "real_photo"


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
    assert f"`{bot.format_public_id(user)}`" in text
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
    assert f"`{bot.format_public_id(target)}`" in reply["text"]
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


# ── MeChat-style cards, onboarding & discovery ──────────────────

def test_profile_card_shows_name_age_city(fresh_db):
    user = register(fresh_db, 1)
    fresh_db.update_name(1, "Rakib")
    fresh_db.update_age(1, 26)
    fresh_db.update_city(1, "Dhaka")
    text = bot.build_profile_text(user)
    assert "Rakib" in text and "26" in text and "Dhaka" in text


def test_user_card_shows_name_age_and_online_status(fresh_db):
    register(fresh_db, 1)
    target = register(fresh_db, 2)
    fresh_db.update_name(2, "Shivani")
    fresh_db.update_age(2, 19)
    fresh_db.update_city(2, "Bangalore")
    fresh_db.pair_users(1, 2)

    text = bot.build_user_card(target, 1)
    assert "Shivani" in text and "19" in text and "Bangalore" in text
    assert "Online (Chatting" in text
    assert f"`{bot.format_public_id(target)}`" in text


def test_profile_card_buttons_match_reference(fresh_db):
    register(fresh_db, 1)
    register(fresh_db, 2)

    query, context = press(1, f"view_{2}")

    # the card always arrives as a photo (default photo when no photo is set)
    assert context.bot.photos, "profile card should be sent as a photo card"
    card = context.bot.photos[-1]
    assert hasattr(card["photo"], "name")  # opened default photo file
    labels = [b.text for b in _buttons(card["reply_markup"])]
    assert labels[0] == "❤️ Like"
    assert any("Direct Message" in label for label in labels)
    assert f"{DIRECT_MESSAGE_COST} 🪙" in next(
        label for label in labels if "Direct Message" in label
    )
    assert any("Chat Request" in label for label in labels)
    assert any("Block User" in label for label in labels)
    assert any("Report User" in label for label in labels)
    assert any("Add to Contacts" in label for label in labels)
    assert any("Notify me when chat ends" in label for label in labels)


def test_profile_card_keeps_photo_and_details_in_one_message(fresh_db):
    register(fresh_db, 1)
    register(fresh_db, 2)
    fresh_db.update_name(2, "Shivani")
    fresh_db.update_age(2, 19)

    query, context = press(1, f"view_{2}")

    assert len(context.bot.photos) == 1  # one card, not a photo + a text below
    card = context.bot.photos[-1]
    assert "Shivani" in card["caption"] and "19" in card["caption"]
    assert card["reply_markup"] is not None


def test_onboarding_collects_name_age_and_city(fresh_db):
    register(fresh_db, 1, complete=False)
    context = FakeContext()
    press(1, "pref_any", context)
    assert context.user_data["awaiting_name"] is True

    update = FakeUpdate(1, message=FakeMessage(text="Rakib"))
    asyncio.run(bot.relay_message(update, context))
    assert fresh_db.get_user(1).name == "Rakib"
    assert context.user_data["awaiting_age"] is True

    update = FakeUpdate(1, message=FakeMessage(text="25"))
    asyncio.run(bot.relay_message(update, context))
    assert fresh_db.get_user(1).age == 25
    assert context.user_data["awaiting_city"] is True

    update = FakeUpdate(1, message=FakeMessage(text="Dhaka"))
    asyncio.run(bot.relay_message(update, context))
    assert fresh_db.get_user(1).city == "Dhaka"
    assert "all set" in update.message.replies[-1]["text"].lower()


def test_invalid_age_is_reasked(fresh_db):
    register(fresh_db, 1, complete=False)
    context = FakeContext()
    context.user_data["awaiting_age"] = True

    update = FakeUpdate(1, message=FakeMessage(text="abc"))
    asyncio.run(bot.relay_message(update, context))

    assert fresh_db.get_user(1).age is None
    assert context.user_data["awaiting_age"] is True


def test_settings_change_name_does_not_start_onboarding(fresh_db):
    register(fresh_db, 1)
    context = FakeContext()
    press(1, "change_name", context)
    update = FakeUpdate(1, message=FakeMessage(text="Rakib"))
    asyncio.run(bot.relay_message(update, context))
    assert fresh_db.get_user(1).name == "Rakib"
    # Settings flow: no age/city prompts afterwards
    assert context.user_data.get("awaiting_age") is not True
    assert context.user_data.get("awaiting_city") is not True


def test_settings_change_age_does_not_force_city(fresh_db):
    register(fresh_db, 1)
    context = FakeContext()
    press(1, "change_age", context)
    update = FakeUpdate(1, message=FakeMessage(text="31"))
    asyncio.run(bot.relay_message(update, context))
    assert fresh_db.get_user(1).age == 31
    assert context.user_data.get("awaiting_city") is not True


# ── Mandatory name / age / city ─────────────────────────────────

def test_search_requires_name_age_and_city(fresh_db):
    register(fresh_db, 1, complete=False)
    context = FakeContext()

    text, markup, mode = asyncio.run(bot.begin_search(context, 1, Gender.ANY))

    assert "required" in text
    assert context.user_data["awaiting_name"] is True
    assert fresh_db.get_user(1).state == ChatState.IDLE

    # completing the chain unlocks the search
    for value in ("Rakib", "25", "Dhaka"):
        update = FakeUpdate(1, message=FakeMessage(text=value))
        asyncio.run(bot.relay_message(update, context))
    text, _, _ = asyncio.run(bot.begin_search(FakeContext(), 1, Gender.ANY))
    assert "Searching" in text


def test_find_command_requires_name_age_and_city(fresh_db):
    register(fresh_db, 1, complete=False)
    context = FakeContext()
    update = FakeUpdate(1)

    asyncio.run(bot.find_command(update, context))

    assert "required" in update.message.replies[0]["text"]
    assert context.user_data["awaiting_name"] is True


def test_browse_requires_name_age_and_city(fresh_db):
    register(fresh_db, 1, complete=False)
    context = FakeContext()
    update = FakeUpdate(1)

    asyncio.run(bot.browse_command(update, context))

    assert "required" in update.message.replies[0]["text"]
    assert context.user_data["awaiting_name"] is True


def test_setup_chain_skips_fields_already_set(fresh_db):
    # only the city is missing → the chain asks for exactly that
    register(fresh_db, 1, complete=False)
    fresh_db.update_name(1, "Rakib")
    fresh_db.update_age(1, 25)
    context = FakeContext()

    text, _, _ = asyncio.run(bot.begin_search(context, 1, Gender.ANY))
    assert "**city** is required" in text
    assert context.user_data.get("awaiting_city") is True
    assert context.user_data.get("awaiting_name") is not True
    assert context.user_data.get("awaiting_age") is not True


def test_viewing_profile_notifies_owner_once(fresh_db):
    register(fresh_db, 1, gender=Gender.MALE)
    register(fresh_db, 2, gender=Gender.FEMALE)

    context = FakeContext()
    press(1, f"view_{2}", context)
    press(1, f"view_{2}", context)

    alerts = [m for m in context.bot.sent if m["chat_id"] == 2]
    assert len(alerts) == 1                      # cooldown-limited
    assert "viewed your profile" in alerts[0]["text"]


def test_viewing_own_profile_never_notifies(fresh_db):
    register(fresh_db, 1)
    context = FakeContext()
    press(1, "view_1", context)
    assert context.bot.sent == []


# ── Direct Message / Block / Report from a card ────────────────

def test_direct_message_charges_one_coin_and_pairs(fresh_db):
    register(fresh_db, 1)
    register(fresh_db, 2, gender=Gender.FEMALE)

    query, context = press(1, f"dm_{2}")

    assert fresh_db.get_user(1).state == ChatState.CHATTING
    assert fresh_db.get_user(2).state == ChatState.CHATTING
    assert fresh_db.get_user(1).coins == STARTING_COINS - DIRECT_MESSAGE_COST
    assert any("Partner found" in p["caption"] for p in context.bot.photos)
    assert "Direct chat started" in query.edits[-1]["text"]
    assert f"-{DIRECT_MESSAGE_COST}" in query.edits[-1]["text"]


def test_direct_message_refused_without_coins(fresh_db):
    user = register(fresh_db, 1)
    user.coins = 0
    register(fresh_db, 2, gender=Gender.FEMALE)

    query, context = press(1, f"dm_{2}")

    assert query.answers[-1]["show_alert"] is True
    assert "Not enough Coins" in query.answers[-1]["text"]
    assert fresh_db.get_user(1).state == ChatState.IDLE
    assert any("Not enough Coins" in m["text"] for m in context.bot.sent)


def test_direct_message_refused_when_busy(fresh_db):
    register(fresh_db, 1)
    register(fresh_db, 2, gender=Gender.FEMALE)
    register(fresh_db, 3)
    fresh_db.add_to_queue(2)
    fresh_db.add_to_queue(3)
    fresh_db.pair_users(2, 3)

    query, _ = press(1, f"dm_{2}")

    assert query.answers[-1]["show_alert"] is True
    assert fresh_db.get_user(1).state == ChatState.IDLE


# ── Forced channel subscription ────────────────────────────────

def _enable_force_join(monkeypatch):
    monkeypatch.setattr(bot, "FORCE_CHANNEL", "@testchan")
    monkeypatch.setattr(bot, "FORCE_CHANNEL_INVITE", "")


def test_force_join_popup_blocks_messages_until_joined(fresh_db, monkeypatch):
    _enable_force_join(monkeypatch)
    register(fresh_db, 1)

    context = FakeContext()
    context.bot.member_status = "left"
    update = FakeUpdate(1, message=FakeMessage(text="hello"))
    asyncio.run(bot.relay_message(update, context))

    assert len(update.message.replies) == 1
    assert "channel" in update.message.replies[0]["text"].lower()
    markup = update.message.replies[0]["reply_markup"]
    urls = [b.url for b in _buttons(markup) if b.url]
    assert urls == ["https://t.me/testchan"]

    # once they join, messages flow again
    context.bot.member_status = "member"
    update2 = FakeUpdate(1, message=FakeMessage(text="hello"))
    asyncio.run(bot.relay_message(update2, context))
    assert all("channel" not in r["text"].lower() for r in update2.message.replies)


def test_force_join_gate_stops_buttons_and_joined_check_works(fresh_db, monkeypatch):
    _enable_force_join(monkeypatch)
    register(fresh_db, 1)
    register(fresh_db, 2, gender=Gender.FEMALE)

    # not joined → the search button is refused with the join popup
    context = FakeContext()
    context.bot.member_status = "left"
    query, _ = press(1, "find_partner", context)
    assert query.answers[-1]["show_alert"] is True
    assert "join" in query.answers[-1]["text"].lower()
    assert any("channel" in m["text"].lower() for m in context.bot.sent)

    # "✅ I've Joined" while still not joined → alert, no menu
    query, _ = press(1, "joined_check", context)
    assert "haven't joined" in query.answers[-1]["text"]
    assert query.edits == []

    # "✅ I've Joined" after joining → menu
    context.bot.member_status = "member"
    query, _ = press(1, "joined_check", context)
    assert "Welcome" in query.answers[-1]["text"]
    assert "Thanks for joining" in query.edits[-1]["text"]


def test_no_force_join_configured_skips_the_gate(fresh_db, monkeypatch):
    monkeypatch.setattr(bot, "FORCE_CHANNEL", "")
    monkeypatch.setattr(bot, "FORCE_CHANNEL_INVITE", "")
    register(fresh_db, 1)

    context = FakeContext()
    context.bot.member_status = "left"   # never asked
    update = FakeUpdate(1, message=FakeMessage(text="hi"))
    asyncio.run(bot.relay_message(update, context))
    assert update.message.replies, "bot should answer without any channel config"


def test_profile_setup_comes_before_force_join(fresh_db, monkeypatch):
    _enable_force_join(monkeypatch)
    register(fresh_db, 1, complete=False)
    context = FakeContext()
    context.bot.member_status = "left"   # hasn't joined the channel yet

    # onboarding runs to completion — the gate waits while fields are missing
    press(1, "pref_any", context)
    for value in ("Rakib", "25", "Dhaka"):
        update = FakeUpdate(1, message=FakeMessage(text=value))
        asyncio.run(bot.relay_message(update, context))
        # input is processed as setup — the gate never answers instead of it
        assert update.message.replies[0]["text"].startswith("✅")

    user = fresh_db.get_user(1)
    assert (user.name, user.age, user.city) == ("Rakib", 25, "Dhaka")

    # profile complete → the join popup lands right after setup
    assert "channel" in update.message.replies[-1]["text"].lower()
    markup = update.message.replies[-1]["reply_markup"]
    assert any(
        b.url == "https://t.me/testchan" for b in _buttons(markup) if b.url
    )


def test_block_from_profile_card_stops_matching(fresh_db):
    register(fresh_db, 1, gender=Gender.MALE, country="US")
    register(fresh_db, 2, gender=Gender.FEMALE, country="FR")
    fresh_db.add_to_queue(1)
    fresh_db.add_to_queue(2)
    assert fresh_db.find_match(1) == 2

    press(1, f"block_{2}")

    fresh_db.add_to_queue(1)
    fresh_db.add_to_queue(2)
    assert fresh_db.find_match(1) is None


def test_report_from_profile_card_bans_at_threshold(fresh_db):
    from database import BAN_REPORT_THRESHOLD
    target = 300
    register(fresh_db, target, gender=Gender.FEMALE)
    for i in range(BAN_REPORT_THRESHOLD):
        reporter = 400 + i
        register(fresh_db, reporter)
        press(reporter, f"rpt_{target}")
    assert fresh_db.get_user(target).banned is True


def test_add_contact_from_profile_card(fresh_db):
    register(fresh_db, 1)
    register(fresh_db, 2)
    query, _ = press(1, f"addc_{2}")
    assert [u.user_id for u in fresh_db.contacts_of(1)] == [2]
    assert "Added" in query.answers[-1]["text"]


# ── 🔔 notify-me-when-chat-ends ────────────────────────────────

def test_notify_on_end_pings_when_chat_ends(fresh_db):
    register(fresh_db, 1)
    register(fresh_db, 2, gender=Gender.FEMALE)
    fresh_db.add_to_queue(1)
    fresh_db.add_to_queue(2)
    fresh_db.pair_users(1, 2)
    fresh_db.set_notify_end(1, True)

    query, context = press(1, "end_chat")

    assert fresh_db.get_user(1).state == ChatState.IDLE
    assert any(
        m["chat_id"] == 1 and "chat has ended" in m["text"]
        for m in context.bot.sent
    )
    assert fresh_db.get_user(1).notify_on_end is False


def test_notify_toggle_switches_the_flag(fresh_db):
    register(fresh_db, 1)
    register(fresh_db, 2)

    press(1, f"notify_{2}")
    assert fresh_db.get_user(1).notify_on_end is True
    press(1, f"notify_{2}")
    assert fresh_db.get_user(1).notify_on_end is False


def test_notify_enable_costs_one_coin_and_disable_is_free(fresh_db):
    register(fresh_db, 1)
    register(fresh_db, 2)
    before = fresh_db.get_user(1).coins

    query, _ = press(1, f"notify_{2}")
    assert fresh_db.get_user(1).notify_on_end is True
    assert fresh_db.get_user(1).coins == before - NOTIFY_COST
    assert f"-{NOTIFY_COST}" in query.answers[-1]["text"]

    press(1, f"notify_{2}")
    assert fresh_db.get_user(1).notify_on_end is False
    assert fresh_db.get_user(1).coins == before - NOTIFY_COST  # no refund, no charge


def test_notify_enable_is_free_for_vip(fresh_db):
    user = register(fresh_db, 1)
    register(fresh_db, 2)
    user.vip = True
    before = user.coins

    query, _ = press(1, f"notify_{2}")

    assert fresh_db.get_user(1).notify_on_end is True
    assert fresh_db.get_user(1).coins == before
    assert "free for VIP" in query.answers[-1]["text"]


def test_notify_enable_is_refused_without_coins(fresh_db):
    user = register(fresh_db, 1)
    register(fresh_db, 2)
    user.coins = 0

    query, _ = press(1, f"notify_{2}")

    assert fresh_db.get_user(1).notify_on_end is False
    assert query.answers[-1]["show_alert"] is True
    assert "Not enough Coins" in query.answers[-1]["text"]
    assert user.coins == 0


# ── ⏰ Daily reminder (one message a day) ────────────────────────

def test_settings_has_the_daily_reminder_toggle(fresh_db):
    register(fresh_db, 1)

    query, _ = press(1, "settings")

    labels = [b.text for b in _buttons(query.edits[-1]["reply_markup"])]
    assert any("Daily Reminder" in label for label in labels)


def test_reminder_toggle_switches_the_flag(fresh_db):
    register(fresh_db, 1)

    query, _ = press(1, "reminder_toggle")
    assert fresh_db.get_user(1).daily_reminder is True
    assert "ON" in query.edits[-1]["text"]
    assert any(
        b.callback_data == "reminder_toggle"
        for b in _buttons(query.edits[-1]["reply_markup"])
    )

    query, _ = press(1, "reminder_toggle")
    assert fresh_db.get_user(1).daily_reminder is False
    assert "OFF" in query.edits[-1]["text"]


def test_daily_reminder_goes_out_once_per_day(fresh_db):
    register(fresh_db, 1)
    fresh_db.set_daily_reminder(1, True)
    context = FakeContext()

    sent = asyncio.run(
        bot.send_due_reminders(context.bot, current_hour=10, today="2030-01-01")
    )
    assert sent == 1
    assert any(
        m["chat_id"] == 1 and "reminder" in m["text"].lower()
        for m in context.bot.sent
    )
    assert fresh_db.get_user(1).reminder_date == "2030-01-01"

    # second sweep the same day stays silent
    assert (
        asyncio.run(
            bot.send_due_reminders(context.bot, current_hour=11, today="2030-01-01")
        )
        == 0
    )
    # outside the waking-hours window nothing goes out
    assert (
        asyncio.run(
            bot.send_due_reminders(context.bot, current_hour=3, today="2030-01-02")
        )
        == 0
    )
    # the next day it goes out again (exactly one message)
    assert (
        asyncio.run(
            bot.send_due_reminders(context.bot, current_hour=10, today="2030-01-02")
        )
        == 1
    )
    assert len([m for m in context.bot.sent if m["chat_id"] == 1]) == 2


def test_users_without_the_reminder_opt_in_get_nothing(fresh_db):
    register(fresh_db, 1)
    context = FakeContext()

    sent = asyncio.run(
        bot.send_due_reminders(context.bot, current_hour=10, today="2030-01-01")
    )

    assert sent == 0
    assert context.bot.sent == []


def test_a_failed_reminder_is_retried_later(fresh_db):
    register(fresh_db, 1)
    fresh_db.set_daily_reminder(1, True)

    class BrokenBot:
        async def send_message(self, **kwargs):
            raise RuntimeError("chat not found")

    sent = asyncio.run(
        bot.send_due_reminders(BrokenBot(), current_hour=10, today="2030-01-01")
    )
    assert sent == 0
    assert fresh_db.get_user(1).reminder_date != "2030-01-01"  # not burned

    context = FakeContext()
    sent = asyncio.run(
        bot.send_due_reminders(context.bot, current_hour=10, today="2030-01-01")
    )
    assert sent == 1


# ── Persistent bottom bar ──────────────────────────────────────

def test_reply_keyboard_starts_random_chat(fresh_db):
    register(fresh_db, 1)
    context = FakeContext()
    update = FakeUpdate(1, message=FakeMessage(text=bot.NEW_CHAT_LABEL))

    asyncio.run(bot.relay_message(update, context))

    assert fresh_db.get_user(1).state == ChatState.SEARCHING


def test_reply_keyboard_opens_browse_menu(fresh_db):
    register(fresh_db, 1)
    other = register(fresh_db, 2, gender=Gender.FEMALE)
    context = FakeContext()
    update = FakeUpdate(1, message=FakeMessage(text=bot.BROWSE_LABEL))

    asyncio.run(bot.relay_message(update, context))

    reply = update.message.replies[0]
    assert "Who do you want to see" in reply["text"]
    assert "brw_ready" in [
        b.callback_data for b in _buttons(reply["reply_markup"])
    ]

    # Picking a category shows the actual list
    query, _ = press(1, "brw_all", context)
    text = query.edits[-1]["text"]
    assert "People online" in text
    assert f"view_{other.user_id}" in [
        b.callback_data for b in _buttons(query.edits[-1]["reply_markup"])
    ]


def test_reply_keyboard_text_is_relayed_while_chatting(fresh_db):
    register(fresh_db, 1)
    register(fresh_db, 2, gender=Gender.FEMALE)
    fresh_db.add_to_queue(1)
    fresh_db.add_to_queue(2)
    fresh_db.pair_users(1, 2)

    context = FakeContext()
    update = FakeUpdate(1, message=FakeMessage(text=bot.NEW_CHAT_LABEL))
    asyncio.run(bot.relay_message(update, context))

    assert fresh_db.get_user(1).state == ChatState.CHATTING
    assert any(m["chat_id"] == 2 for m in context.bot.sent)


# ── Browse / swipe ─────────────────────────────────────────────

def test_browse_command_shows_category_menu(fresh_db):
    register(fresh_db, 1)
    other = register(fresh_db, 2, gender=Gender.FEMALE)
    fresh_db.update_name(2, "Shivani")
    fresh_db.update_age(2, 19)
    fresh_db.update_city(2, "Bangalore")

    context = FakeContext()
    update = FakeUpdate(1)
    asyncio.run(bot.browse_command(update, context))

    menu = update.message.replies[0]["text"]
    assert "Who do you want to see" in menu
    menu_buttons = [
        b.callback_data
        for b in _buttons(update.message.replies[0]["reply_markup"])
    ]
    assert "brw_myage" in menu_buttons and "brw_popular" in menu_buttons

    query, _ = press(1, "brw_all", context)
    text = query.edits[-1]["text"]
    assert "Shivani" in text and "Bangalore" in text
    assert bot.public_id_slug(other) in text


def test_browse_more_extends_the_list(fresh_db):
    register(fresh_db, 1)
    for i in range(2, 9):
        register(fresh_db, i)
    context = FakeContext()
    press(1, "browse_more", context)
    first_page = len(context.user_data["browse_ids"])
    press(1, "browse_more", context)
    assert len(context.user_data["browse_ids"]) > first_page


def test_swipe_shows_one_profile_at_a_time(fresh_db):
    register(fresh_db, 1)
    register(fresh_db, 2)
    context = FakeContext()
    press(1, "browse_more", context)      # populates the browse list
    press(1, "browse_swipe", context)
    assert context.user_data["swipe_ids"] == [2]

    query, _ = press(1, "swipe_0", context)
    assert "Profile 1 of 1" in query.edits[-1]["text"]


def test_swipe_out_of_range_is_refused(fresh_db):
    register(fresh_db, 1)
    register(fresh_db, 2)
    context = FakeContext()
    press(1, "browse_more", context)
    press(1, "browse_swipe", context)

    query, _ = press(1, "swipe_9", context)

    assert query.answers[-1]["text"] == "No more profiles."
    assert query.edits == []


# ── VIP ────────────────────────────────────────────────────────

def test_vip_girl_search_is_free(fresh_db):
    user = register(fresh_db, 1)
    user.vip = True

    text, _, _ = asyncio.run(bot.begin_search(FakeContext(), 1, Gender.FEMALE))

    assert fresh_db.get_user(1).coins == STARTING_COINS
    assert fresh_db.get_user(1).state == ChatState.SEARCHING


def test_vip_payment_sets_the_flag(fresh_db):
    register(fresh_db, 1)
    update = FakeUpdate(1)
    update.message.successful_payment = FakePayment("coin_pack:1:6200")

    asyncio.run(bot.payment_success_handler(update, FakeContext()))

    assert fresh_db.get_user(1).vip is True


def test_vip_text_mentions_free_girl_search(fresh_db):
    user = register(fresh_db, 1)
    assert "Girl searches" in bot.vip_text(user)


# ── Chat request TTL ───────────────────────────────────────────

def test_request_expires_and_refunds_the_sender(fresh_db):
    import time as _time
    from database import CHAT_REQUEST_TTL

    sender = register(fresh_db, 1)
    register(fresh_db, 2)
    fresh_db.create_request(1, 2)
    fresh_db.requests["1:2"]["created_at"] = _time.time() - CHAT_REQUEST_TTL - 5

    assert fresh_db.request_status(1, 2) == "expired"
    assert sender.coins == STARTING_COINS        # refunded
    assert fresh_db.resolve_request(1, 2, accepted=True) is False


def test_expired_request_can_be_sent_again(fresh_db):
    import time as _time
    from database import CHAT_REQUEST_TTL

    register(fresh_db, 1)
    register(fresh_db, 2)
    fresh_db.create_request(1, 2)
    fresh_db.requests["1:2"]["created_at"] = _time.time() - CHAT_REQUEST_TTL - 5

    ok, _ = fresh_db.create_request(1, 2)
    assert ok is True
    assert fresh_db.request_status(1, 2) == "pending"


def test_request_notification_uses_view_button(fresh_db):
    register(fresh_db, 1)
    register(fresh_db, 2)

    query, context = press(1, f"req_chat_{2}")

    delivered = [m for m in context.bot.sent if m["chat_id"] == 2]
    labels = [b.text for b in _buttons(delivered[0]["reply_markup"])]
    assert any("View Chat Request" in label for label in labels)


def test_view_request_shows_accept_buttons(fresh_db):
    register(fresh_db, 1)
    register(fresh_db, 2)
    fresh_db.create_request(1, 2)

    query, _ = press(2, "req_view_1")

    labels = [b.text for b in _buttons(query.edits[-1]["reply_markup"])]
    assert "✅ Accept" in labels and "❌ Decline" in labels


# -- MeChat-style extras: blocked list, DM privacy, match reward --

def test_blocked_list_menu_and_unblock(fresh_db):
    register(fresh_db, 1)
    register(fresh_db, 2)
    fresh_db.block_user(1, 2)

    query, context = press(1, "blocked_list")
    text = query.edits[-1]["text"]
    assert "Blocked Users" in text
    labels = [b.callback_data for b in _buttons(query.edits[-1]["reply_markup"])]
    assert "unblock_2" in labels

    query2, _ = press(1, "unblock_2", context)
    assert fresh_db.get_user(1).blocked == set()
    assert "No blocked users" in query2.edits[-1]["text"]


def test_direct_message_is_hidden_until_viewed(fresh_db):
    sender = register(fresh_db, 1)
    receiver = register(fresh_db, 2)
    context = FakeContext()
    context.user_data["browse_ids"] = [2]
    context.user_data["awaiting_broadcast"] = True

    update = FakeUpdate(1, message=FakeMessage(text="secret hello"))
    asyncio.run(bot.relay_message(update, context))

    # Receiver got the privacy wrapper, NOT the content
    assert any(
        m["chat_id"] == receiver.user_id and "direct message" in m["text"]
        for m in context.bot.sent
    )
    assert not any("secret hello" in m["text"] for m in context.bot.sent)
    # Content is stored, waiting to be revealed
    assert fresh_db.pending_dms[receiver.user_id]["text"] == "secret hello"


def test_view_msg_reveals_stored_dm(fresh_db):
    sender = register(fresh_db, 1)
    receiver = register(fresh_db, 2)
    fresh_db.queue_dm(2, 1, "the secret text")

    query, _ = press(2, "view_msg_1")
    text = query.edits[-1]["text"]
    assert "the secret text" in text
    assert "Shivani" not in text  # sanity: no crash on unnamed users
    assert fresh_db.pop_dm(2) is None  # consumed


def test_match_awards_free_coin_to_girls_only(fresh_db):
    register(fresh_db, 1, gender=Gender.MALE, country="US")
    register(fresh_db, 2, gender=Gender.FEMALE, country="FR")
    fresh_db.add_to_queue(2, search_pref=Gender.ANY)
    start1 = fresh_db.get_user(1).coins
    start2 = fresh_db.get_user(2).coins

    context = FakeContext()
    text, markup, mode = run(bot.begin_search(context, 1, Gender.ANY))

    assert "Partner found" in text
    # Girl got the free coin, boy didn't
    assert fresh_db.get_user(1).coins == start1
    assert fresh_db.get_user(2).coins == start2 + bot.DAILY_REWARD_COINS
    # Only the girl's match card carries the free-coin line
    coin_cards = [p for p in context.bot.photos if "free coin" in p["caption"]]
    assert len(coin_cards) == 1 and coin_cards[0]["chat_id"] == 2


def test_my_profile_sends_photo_card(fresh_db):
    user = register(fresh_db, 1)
    fresh_db.set_photo(1, "photo_xyz")

    query, context = press(1, "my_profile")

    # The card goes out as a photo message, so the original message is not edited
    assert query.edits == [] or "coins" in query.edits[-1]["text"].lower()


# ── Dedicated backup bot (BACKUP_BOT_TOKEN) ──────────────────────

def test_backup_bot_defaults_to_main_bot(fresh_db, monkeypatch):
    """No BACKUP_BOT_TOKEN: the main bot handles backups itself."""
    monkeypatch.setattr(bot, "BACKUP_BOT_TOKEN", "")
    monkeypatch.setattr(bot, "BACKUP_CHANNEL", "-100123")
    monkeypatch.setattr(bot.db, "path", "bot.db")
    main = object()
    assert run(bot._get_backup_bot(main)) is main


def test_backup_bot_disabled_when_no_channel(fresh_db, monkeypatch):
    """Backups off entirely: never builds a second bot, even with a token."""
    monkeypatch.setattr(bot, "BACKUP_BOT_TOKEN", "123456:backup-token")
    monkeypatch.setattr(bot, "BACKUP_CHANNEL", "")
    main = object()
    assert run(bot._get_backup_bot(main)) is main


def test_backup_bot_uses_dedicated_token(monkeypatch):
    """With a channel + BACKUP_BOT_TOKEN, a separate bot is created once."""
    created = []

    class FakeBot:
        def __init__(self, token):
            created.append(token)
            self.token = token

        async def initialize(self):
            self.ready = True

    monkeypatch.setattr(bot, "Bot", FakeBot)
    monkeypatch.setattr(bot, "BACKUP_BOT_TOKEN", "111:backup")
    monkeypatch.setattr(bot, "BACKUP_CHANNEL", "-100123")
    monkeypatch.setattr(bot, "_dedicated_backup_bot", None)
    monkeypatch.setattr(bot.db, "path", "bot.db")

    main = object()
    first = run(bot._get_backup_bot(main))
    second = run(bot._get_backup_bot(main))
    assert first is not main and first.token == "111:backup"
    assert second is first          # created only once
    assert created == ["111:backup"]
    monkeypatch.setattr(bot, "_dedicated_backup_bot", None)


def test_backup_bot_falls_back_on_bad_token(monkeypatch):
    """An unusable BACKUP_BOT_TOKEN must not kill startup: falls back."""
    class BadBot:
        def __init__(self, token):
            pass

        async def initialize(self):
            raise RuntimeError("Unauthorized")

    monkeypatch.setattr(bot, "Bot", BadBot)
    monkeypatch.setattr(bot, "BACKUP_BOT_TOKEN", "999:bad")
    monkeypatch.setattr(bot, "BACKUP_CHANNEL", "-100123")
    monkeypatch.setattr(bot, "_dedicated_backup_bot", None)
    monkeypatch.setattr(bot.db, "path", "bot.db")

    main = object()
    assert run(bot._get_backup_bot(main)) is main
    monkeypatch.setattr(bot, "_dedicated_backup_bot", None)


# ── Restore on a fresh deploy (the "bot started from zero" bug) ──

def _channel_with_backup(backup_path, age_hours=1):
    """A fake backup channel holding `backup_path` as the pinned bot.db."""
    import shutil
    from datetime import datetime, timedelta

    class FakeFile:
        async def download_to_drive(self, to):
            shutil.copyfile(backup_path, to)

    class FakeDocument:
        file_name = "bot.db"

        async def get_file(self):
            return FakeFile()

    class FakeMsg:
        date = datetime.now() - timedelta(hours=age_hours)
        document = FakeDocument()

    class FakeChat:
        pinned_message = FakeMsg()

    class FakeChannelBot:
        async def get_chat(self, chat_id):
            return FakeChat()

    return FakeChannelBot()


def _backup_file_with(tmp_path, name, user_ids):
    from database import Database

    path = str(tmp_path / name)
    db_file = Database(path=path)
    for uid in user_ids:
        db_file.register_user(uid)
    db_file.close()
    return path


def test_fresh_empty_db_restores_from_an_older_channel_backup(tmp_path, monkeypatch):
    """bot.db is created EMPTY at boot, so its mtime is always newer than the
    channel backup. Skipping the restore there is what made redeploys start
    from zero (and then wipe the backup) — the empty DB must still restore."""
    from database import Database

    backup_path = _backup_file_with(tmp_path, "channel.db", [111, 222])
    local = Database(path=str(tmp_path / "bot.db"))  # empty, mtime = now
    assert local.users == {}

    monkeypatch.setattr(bot, "db", local)
    monkeypatch.setattr(bot, "BACKUP_CHANNEL", "-100123")
    monkeypatch.setattr(bot, "BACKUP_BOT_TOKEN", "")
    monkeypatch.setattr(bot, "_RESTORE_SKIPPED", False)
    monkeypatch.setattr(bot, "_BACKUP_MSG", {"id": None, "hash": None})

    run(bot.restore_db_from_backup(_channel_with_backup(backup_path)))

    assert len(local.users) == 2
    assert bot._RESTORE_SKIPPED is False


def test_local_db_with_users_is_kept_when_the_backup_is_older(tmp_path, monkeypatch):
    """Persistent volume: real local users must not be replaced by an older
    snapshot from the channel."""
    from database import Database

    backup_path = _backup_file_with(tmp_path, "channel.db", [111, 222])
    local = Database(path=str(tmp_path / "bot.db"))
    for uid in (1, 2, 3):
        local.register_user(uid)

    monkeypatch.setattr(bot, "db", local)
    monkeypatch.setattr(bot, "BACKUP_CHANNEL", "-100123")
    monkeypatch.setattr(bot, "_RESTORE_SKIPPED", False)
    monkeypatch.setattr(bot, "_BACKUP_MSG", {"id": None, "hash": None})

    run(bot.restore_db_from_backup(_channel_with_backup(backup_path, age_hours=1)))

    assert [u for u in sorted(local.users)] == [1, 2, 3]


def test_failed_restore_blocks_the_upload_that_would_wipe_the_backup(
    tmp_path, monkeypatch
):
    """If the channel backup could never be loaded, an empty local DB must
    never be uploaded — that would delete the last good snapshot."""
    from database import Database

    local = Database(path=str(tmp_path / "bot.db"))

    class BrokenBot:
        async def get_chat(self, chat_id):
            raise RuntimeError("Forbidden: bot is not admin")

    monkeypatch.setattr(bot, "db", local)
    monkeypatch.setattr(bot, "BACKUP_CHANNEL", "-100123")
    monkeypatch.setattr(bot, "_RESTORE_SKIPPED", False)

    run(bot.restore_db_from_backup(BrokenBot()))

    assert bot._RESTORE_SKIPPED is True

    uploads = []

    class Recorder:
        async def send_document(self, **kwargs):
            uploads.append(kwargs)
            raise AssertionError("upload must not run")

    local.path = str(tmp_path / "bot.db")
    assert run(bot.upload_db_backup(Recorder())) is False
    assert uploads == []


def test_a_failed_restore_with_local_users_allows_normal_backups(
    tmp_path, monkeypatch
):
    """The flag is only for 'we have nothing': local data keeps backing up."""
    from database import Database

    local = Database(path=str(tmp_path / "bot.db"))
    local.register_user(1)

    class BrokenBot:
        async def get_chat(self, chat_id):
            raise RuntimeError("Forbidden")

    monkeypatch.setattr(bot, "db", local)
    monkeypatch.setattr(bot, "BACKUP_CHANNEL", "-100123")
    monkeypatch.setattr(bot, "_RESTORE_SKIPPED", False)

    run(bot.restore_db_from_backup(BrokenBot()))

    assert bot._RESTORE_SKIPPED is False


def test_after_a_successful_restore_the_startup_upload_changes_nothing(
    tmp_path, monkeypatch
):
    """Restored DB == channel backup → the upload must skip instead of
    re-sending and deleting the snapshot it just loaded."""
    from database import Database

    backup_path = _backup_file_with(tmp_path, "channel.db", [111, 222])
    local = Database(path=str(tmp_path / "bot.db"))

    monkeypatch.setattr(bot, "db", local)
    monkeypatch.setattr(bot, "BACKUP_CHANNEL", "-100123")
    monkeypatch.setattr(bot, "_RESTORE_SKIPPED", False)
    monkeypatch.setattr(bot, "_BACKUP_MSG", {"id": None, "hash": None})

    run(bot.restore_db_from_backup(_channel_with_backup(backup_path)))
    assert len(local.users) == 2

    uploads = []

    class Recorder:
        async def send_document(self, **kwargs):
            uploads.append(kwargs)
            return SimpleNamespace(message_id=99)

        async def pin_chat_message(self, *args, **kwargs):
            pass

        async def delete_message(self, *args, **kwargs):
            pass

    assert run(bot.upload_db_backup(Recorder())) is False
    assert uploads == []


def test_full_deploy_cycle_keeps_the_member_list_alive(tmp_path, monkeypatch):
    """Replay the real lifecycle: 200 members → bot backs up → redeploy on a
    wiped disk → restore brings all 200 back → the new run does NOT replace
    the channel backup. This is the whole point of the backup bot."""
    import shutil
    from datetime import datetime
    from database import Database

    channel_copy = str(tmp_path / "channel-bot.db")  # what the channel holds

    class FakeDocFile:
        async def download_to_drive(self, to):
            shutil.copyfile(channel_copy, to)

    class FakeDocument:
        file_name = "bot.db"

        async def get_file(self):
            return FakeDocFile()

    class FakeMsg:
        message_id = 7

        def __init__(self):
            self.date = datetime.now()
            self.document = FakeDocument()

    class FakeChat:
        pinned_message = FakeMsg()

    class FakeChannelBot:
        async def get_chat(self, chat_id):
            return FakeChat()

        async def send_document(self, chat_id, document, filename, caption):
            shutil.copyfile(document.name, channel_copy)
            return FakeMsg()

        async def pin_chat_message(self, *args, **kwargs):
            pass

        async def delete_message(self, *args, **kwargs):
            pass

    channel = FakeChannelBot()

    # ── deploy #1: the bot everyone joined ──
    first_run = Database(path=str(tmp_path / "run1" / "bot.db"))
    for uid in range(1, 201):
        first_run.register_user(uid)
    assert len(first_run.users) == 200

    monkeypatch.setattr(bot, "db", first_run)
    monkeypatch.setattr(bot, "BACKUP_CHANNEL", "-100123")
    monkeypatch.setattr(bot, "_RESTORE_SKIPPED", False)
    monkeypatch.setattr(bot, "_BACKUP_MSG", {"id": None, "hash": None})
    assert run(bot.upload_db_backup(channel)) is True  # backup lands in channel

    # ── deploy #2: wiped disk, empty bot.db created at boot ──
    second_run = Database(path=str(tmp_path / "run2" / "bot.db"))
    assert second_run.users == {}

    monkeypatch.setattr(bot, "db", second_run)
    monkeypatch.setattr(bot, "_RESTORE_SKIPPED", False)
    monkeypatch.setattr(bot, "_BACKUP_MSG", {"id": None, "hash": None})

    run(bot.restore_db_from_backup(channel))
    assert len(second_run.users) == 200  # ← the fix: all members are back
    assert bot._RESTORE_SKIPPED is False

    # and the startup upload must not touch the snapshot it just restored
    assert run(bot.upload_db_backup(channel)) is False

    restored_copy = Database(path=channel_copy)
    assert len(restored_copy.users) == 200  # channel still holds the real data


def test_restore_recovers_the_real_backup_from_a_clobbered_channel(
    tmp_path, monkeypatch
):
    """The broken run pinned a 1-user bot.db on top of the real one. The
    restore must look past the pinned file and bring back the snapshot that
    actually holds the members — even if it is older than the local file."""
    import shutil
    from datetime import datetime, timedelta
    from database import Database

    good = _backup_file_with(tmp_path, "good.db", range(1, 201))  # 200 members
    bad = _backup_file_with(tmp_path, "bad.db", [999])  # the clobbered upload

    class FakeDocFile:
        def __init__(self, path):
            self.path = path

        async def download_to_drive(self, to):
            shutil.copyfile(self.path, to)

    class FakeDocument:
        def __init__(self, path):
            self.file_name = "bot.db"
            self.path = path

        async def get_file(self):
            return FakeDocFile(self.path)

    class FakeMsg:
        def __init__(self, mid, path, age_hours):
            self.message_id = mid
            self.date = datetime.now() - timedelta(hours=age_hours)
            self.document = FakeDocument(path)

    bad_msg = FakeMsg(10, bad, 1)  # newest — pinned by the broken run
    good_msg = FakeMsg(9, good, 48)  # older, but holds all 200 members

    class FakeChannelBot:
        async def get_chat(self, chat_id):
            class Chat:
                pinned_message = bad_msg

            return Chat()

        async def get_chat_history(self, chat_id, limit):
            for m in (bad_msg, good_msg):
                yield m

    # the bot already restarted and collected a few members of its own
    local = Database(path=str(tmp_path / "bot.db"))
    for uid in (501, 502, 503):
        local.register_user(uid)

    monkeypatch.setattr(bot, "db", local)
    monkeypatch.setattr(bot, "BACKUP_CHANNEL", "-100123")
    monkeypatch.setattr(bot, "_RESTORE_SKIPPED", False)
    monkeypatch.setattr(bot, "_BACKUP_MSG", {"id": None, "hash": None})

    run(bot.restore_db_from_backup(FakeChannelBot()))

    assert len(local.users) == 200  # all the real members are back
    assert 999 not in local.users and 1 in local.users


def test_upload_keeps_the_last_five_snapshots(tmp_path, monkeypatch):
    """Old backups used to be deleted after EVERY upload — one bad upload
    destroyed the last good copy. Now the newest BACKUP_KEEP stay."""
    from database import Database

    local = Database(path=str(tmp_path / "bot.db"))
    local.register_user(1)

    docs = [
        SimpleNamespace(
            message_id=mid, document=SimpleNamespace(file_name="bot.db")
        )
        for mid in range(100, 92, -1)
    ]

    class Recorder:
        async def get_chat_history(self, chat_id, limit):
            for m in docs:
                yield m

        async def get_chat(self, chat_id):
            raise RuntimeError("no admin rights for get_chat")

        async def send_document(self, **kwargs):
            return SimpleNamespace(message_id=200)

        async def pin_chat_message(self, *args, **kwargs):
            pass

        async def delete_message(self, chat_id, message_id):
            deleted.append(message_id)

    deleted = []
    monkeypatch.setattr(bot, "db", local)
    monkeypatch.setattr(bot, "BACKUP_CHANNEL", "-100123")
    monkeypatch.setattr(bot, "_RESTORE_SKIPPED", False)
    monkeypatch.setattr(bot, "_BACKUP_MSG", {"id": None, "hash": None})
    monkeypatch.setattr(bot, "BACKUP_KEEP", 5)

    assert run(bot.upload_db_backup(Recorder())) is True

    assert deleted == [96, 95, 94, 93]  # only beyond the 5 newest
    assert set(deleted).isdisjoint({100, 99, 98, 97})


# ── GitHub backup (online, every version kept forever) ────────────

def _enable_github(monkeypatch):
    """Point the bot at a GitHub backup repo (network faked in tests)."""
    monkeypatch.setattr(bot, "BACKUP_CHANNEL", "")  # github-only
    monkeypatch.setattr(bot, "BACKUP_GITHUB_REPO", "me/backups")
    monkeypatch.setattr(bot, "BACKUP_GITHUB_TOKEN", "token")
    monkeypatch.setattr(bot, "_RESTORE_SKIPPED", False)
    monkeypatch.setattr(
        bot, "_BACKUP_MSG", {"id": None, "hash": None, "gh_hash": None}
    )


def test_github_restore_picks_the_version_with_the_most_members(
    tmp_path, monkeypatch
):
    """The repo holds every commit — restore probes them and brings back the
    version with the real member list, not the newest broken one."""
    from datetime import datetime, timedelta
    from database import Database

    good = _backup_file_with(tmp_path, "good.db", range(1, 201))
    bad = _backup_file_with(tmp_path, "bad.db", [999])
    with open(good, "rb") as fh:
        good_bytes = fh.read()
    with open(bad, "rb") as fh:
        bad_bytes = fh.read()

    async def fake_versions(limit):
        return [
            {"sha": "aaaa1111", "date": datetime.now()},
            {"sha": "bbbb2222", "date": datetime.now() - timedelta(days=2)},
        ]

    async def fake_download(sha):
        return good_bytes if sha == "bbbb2222" else bad_bytes

    local = Database(path=str(tmp_path / "bot.db"))
    monkeypatch.setattr(bot, "db", local)
    _enable_github(monkeypatch)
    monkeypatch.setattr(bot, "_github_fetch_versions", fake_versions)
    monkeypatch.setattr(bot, "_github_download", fake_download)

    run(bot.restore_db_from_backup(object()))

    assert len(local.users) == 200
    assert bot._RESTORE_SKIPPED is False


def test_github_upload_commits_the_snapshot(tmp_path, monkeypatch):
    from database import Database

    local = Database(path=str(tmp_path / "bot.db"))
    for uid in (1, 2, 3):
        local.register_user(uid)

    sent = {}

    async def fake_upload(data, message):
        sent["data"] = data
        sent["message"] = message
        return True

    monkeypatch.setattr(bot, "db", local)
    _enable_github(monkeypatch)
    monkeypatch.setattr(bot, "_github_upload", fake_upload)

    assert run(bot.upload_db_backup(object())) is True
    with open(local.path, "rb") as fh:
        assert sent["data"] == fh.read()
    assert "3 members" in sent["message"]

    # unchanged database → no duplicate commit
    assert run(bot.upload_db_backup(object())) is False
    assert bot._BACKUP_MSG["gh_hash"] is not None


def test_github_backup_survives_a_broken_channel(tmp_path, monkeypatch):
    """One dead target must never block the other."""
    from database import Database

    local = Database(path=str(tmp_path / "bot.db"))
    local.register_user(1)

    async def fake_upload(data, message):
        return True

    class BrokenChannelBot:
        async def send_document(self, **kwargs):
            raise RuntimeError("channel gone")

    monkeypatch.setattr(bot, "db", local)
    monkeypatch.setattr(bot, "BACKUP_CHANNEL", "-100123")
    monkeypatch.setattr(bot, "BACKUP_GITHUB_REPO", "me/backups")
    monkeypatch.setattr(bot, "BACKUP_GITHUB_TOKEN", "token")
    monkeypatch.setattr(bot, "_RESTORE_SKIPPED", False)
    monkeypatch.setattr(
        bot, "_BACKUP_MSG", {"id": None, "hash": None, "gh_hash": None}
    )
    monkeypatch.setattr(bot, "_github_upload", fake_upload)

    assert run(bot.upload_db_backup(BrokenChannelBot())) is True  # GitHub went out
    assert bot._BACKUP_MSG["gh_hash"] is not None  # committed
    assert bot._BACKUP_MSG["hash"] is None  # channel still pending, no crash


def test_a_channel_restore_still_seeds_github(tmp_path, monkeypatch):
    """The file was loaded FROM the channel — GitHub has never seen it, so
    the first upload must commit it there even though nothing changed."""
    from database import Database

    backup_path = _backup_file_with(tmp_path, "channel.db", [111, 222])
    local = Database(path=str(tmp_path / "bot.db"))

    monkeypatch.setattr(bot, "db", local)
    monkeypatch.setattr(bot, "BACKUP_CHANNEL", "-100123")
    monkeypatch.setattr(bot, "BACKUP_GITHUB_REPO", "me/backups")
    monkeypatch.setattr(bot, "BACKUP_GITHUB_TOKEN", "token")
    monkeypatch.setattr(bot, "_RESTORE_SKIPPED", False)
    monkeypatch.setattr(
        bot, "_BACKUP_MSG", {"id": None, "hash": None, "gh_hash": None}
    )

    async def no_github_versions(limit):
        return []

    monkeypatch.setattr(bot, "_github_fetch_versions", no_github_versions)

    run(bot.restore_db_from_backup(_channel_with_backup(backup_path)))
    assert len(local.users) == 2
    assert bot._BACKUP_MSG["hash"] is not None  # channel already holds it
    assert bot._BACKUP_MSG["gh_hash"] is None  # GitHub does not

    sent = {}

    async def fake_upload(data, message):
        sent["message"] = message
        return True

    monkeypatch.setattr(bot, "_github_upload", fake_upload)

    channel_uploads = []

    class Recorder:
        async def send_document(self, **kwargs):
            channel_uploads.append(kwargs)
            return SimpleNamespace(message_id=99)

        async def pin_chat_message(self, *args, **kwargs):
            pass

        async def delete_message(self, *args, **kwargs):
            pass

    assert run(bot.upload_db_backup(Recorder())) is True
    assert "2 members" in sent["message"]
    assert channel_uploads == []  # channel copy already exists → skipped


def test_a_github_restore_still_seeds_the_channel(tmp_path, monkeypatch):
    """Mirror of the test above: restored from GitHub → the channel gets its
    first copy right away."""
    from datetime import datetime
    from database import Database

    gh_file = _backup_file_with(tmp_path, "gh.db", [111, 222])
    with open(gh_file, "rb") as fh:
        gh_bytes = fh.read()
    local = Database(path=str(tmp_path / "bot.db"))

    async def fake_versions(limit):
        return [{"sha": "abc12345", "date": datetime.now()}]

    async def fake_download(sha):
        return gh_bytes

    class NoChannelHistory:
        async def get_chat(self, chat_id):
            class Chat:
                pinned_message = None

            return Chat()

    monkeypatch.setattr(bot, "db", local)
    monkeypatch.setattr(bot, "BACKUP_CHANNEL", "-100123")
    monkeypatch.setattr(bot, "BACKUP_GITHUB_REPO", "me/backups")
    monkeypatch.setattr(bot, "BACKUP_GITHUB_TOKEN", "token")
    monkeypatch.setattr(bot, "_github_fetch_versions", fake_versions)
    monkeypatch.setattr(bot, "_github_download", fake_download)
    monkeypatch.setattr(bot, "_RESTORE_SKIPPED", False)
    monkeypatch.setattr(
        bot, "_BACKUP_MSG", {"id": None, "hash": None, "gh_hash": None}
    )

    run(bot.restore_db_from_backup(NoChannelHistory()))
    assert len(local.users) == 2
    assert bot._BACKUP_MSG["gh_hash"] is not None  # GitHub already holds it
    assert bot._BACKUP_MSG["hash"] is None  # channel does not

    gh_calls = []

    async def fake_upload(data, message):
        gh_calls.append(message)
        return True

    monkeypatch.setattr(bot, "_github_upload", fake_upload)

    channel_uploads = []

    class Recorder:
        async def send_document(self, **kwargs):
            channel_uploads.append(kwargs)
            return SimpleNamespace(message_id=77)

        async def pin_chat_message(self, *args, **kwargs):
            pass

        async def delete_message(self, *args, **kwargs):
            pass

    assert run(bot.upload_db_backup(Recorder())) is True
    assert len(channel_uploads) == 1  # channel seeded
    assert gh_calls == []  # GitHub already has this exact snapshot → skipped


# ── Tappable public IDs (tap /user_xxx → open that profile) ──────

def test_public_id_link_falls_back_to_code_span(fresh_db):
    user = register(fresh_db, 2)
    assert bot.public_id_link(user) == f"`{bot.format_public_id(user)}`"


def test_public_id_link_becomes_profile_deep_link(fresh_db, monkeypatch):
    monkeypatch.setattr(bot, "_bot_username", "talkNhappybot")
    user = register(fresh_db, 2)
    slug = bot.public_id_slug(user)
    assert bot.public_id_link(user) == (
        f"[{bot.format_public_id(user)}]"
        f"(https://t.me/talkNhappybot?start=chat_{slug})"
    )


def test_match_card_carries_tappable_id(fresh_db, monkeypatch):
    monkeypatch.setattr(bot, "_bot_username", "talkNhappybot")
    register(fresh_db, 1, gender=Gender.MALE, country="US")
    register(fresh_db, 2, gender=Gender.FEMALE, country="FR")
    fresh_db.add_to_queue(2, search_pref=None)
    ctx = FakeContext()

    text, _, _ = run(bot.begin_search(ctx, 1, Gender.FEMALE))

    assert "Partner found" in text
    assert len(ctx.bot.photos) == 2
    for card in ctx.bot.photos:
        assert "https://t.me/talkNhappybot?start=chat_" in card["caption"]


def test_user_id_command_opens_profile(fresh_db):
    register(fresh_db, 1)
    target = register(fresh_db, 2, gender=Gender.FEMALE)
    context = FakeContext()
    update = FakeUpdate(1, message=FakeMessage(text=f"/{bot.public_id_slug(target)}"))

    run(bot.user_id_command(update, context))

    reply = update.message.replies[0]
    assert f"`{bot.format_public_id(target)}`" in reply["text"]
    labels = [b.text for b in _buttons(reply["reply_markup"])]
    assert any("Like" in label for label in labels)


def test_user_id_command_unknown_id(fresh_db):
    register(fresh_db, 1)
    context = FakeContext()
    update = FakeUpdate(1, message=FakeMessage(text="/user_zzzz"))

    run(bot.user_id_command(update, context))

    assert "No account found" in update.message.replies[0]["text"]


def test_user_id_command_own_id(fresh_db):
    user = register(fresh_db, 1)
    context = FakeContext()
    update = FakeUpdate(1, message=FakeMessage(text=f"/{bot.public_id_slug(user)}"))

    run(bot.user_id_command(update, context))

    assert "your own ID" in update.message.replies[0]["text"]


def test_id_search_accepts_user_slug(fresh_db):
    register(fresh_db, 1)
    target = register(fresh_db, 2, gender=Gender.FEMALE)
    context = FakeContext()
    context.user_data["awaiting_id"] = True
    update = FakeUpdate(
        1, message=FakeMessage(text=f"/{bot.public_id_slug(target)}")
    )

    run(bot.relay_message(update, context))

    reply = update.message.replies[0]
    assert f"`{bot.format_public_id(target)}`" in reply["text"]


# ── 👤 Partner Profile / ⬅️ Back on the match card ───────────────

def test_chat_keyboard_has_partner_profile_button():
    labels = [b.callback_data for b in _buttons(bot.chat_keyboard())]
    assert "pview" in labels
    assert "secure_chat" in labels
    assert "end_chat" in labels
    assert "report_partner" in labels


def test_pview_flips_match_card_and_pback_restores_it(fresh_db):
    register(fresh_db, 1, gender=Gender.MALE, country="US")
    register(fresh_db, 2, gender=Gender.FEMALE, country="FR")
    fresh_db.add_to_queue(1)
    fresh_db.add_to_queue(2)
    assert fresh_db.find_match(1) == 2
    fresh_db.pair_users(1, 2)

    context = FakeContext()
    match_text = "🎉 **Partner found!** ... card body ..."
    context.user_data["match_card"] = (2, match_text)

    # 👤 Partner Profile turns the card into the partner's profile
    query, _ = press(1, "pview", context)
    text = query.edits[-1]["text"]
    assert "Age:" in text and "ID:" in text
    labels = [b.callback_data for b in _buttons(query.edits[-1]["reply_markup"])]
    assert "pback" in labels
    assert "dm_2" in labels  # full profile actions are available in-chat

    # ⬅️ Back flips the very same message back to the match card
    query2, _ = press(1, "pback", context)
    assert query2.edits[-1]["text"] == match_text
    labels2 = [b.callback_data for b in _buttons(query2.edits[-1]["reply_markup"])]
    assert "secure_chat" in labels2 and "pview" in labels2


# ── 🔐 Secure Chat (MeChat-style) ───────────────────────────────

def _paired(fresh_db, a=1, b=2):
    register(fresh_db, a, gender=Gender.MALE, country="US")
    register(fresh_db, b, gender=Gender.FEMALE, country="FR")
    fresh_db.add_to_queue(a)
    fresh_db.add_to_queue(b)
    fresh_db.pair_users(a, b)


def test_secure_chat_toggle_sets_both_and_notifies(fresh_db):
    _paired(fresh_db)
    assert fresh_db.get_user(1).secure_chat is False

    query, ctx = press(1, "secure_chat")

    # Both partners are flagged, so the toggle stays in sync.
    assert fresh_db.get_user(1).secure_chat is True
    assert fresh_db.get_user(2).secure_chat is True
    # The match-card button now reflects the ON state.
    labels = [b.callback_data for b in _buttons(query.edits[-1]["reply_markup"])]
    assert "secure_chat" in labels
    # The partner got the "Private chat activated" notice.
    assert any("Private chat activated" in m["text"] for m in ctx.bot.sent)


def test_secure_chat_toggle_off(fresh_db):
    _paired(fresh_db)
    press(1, "secure_chat")          # on
    query, ctx = press(1, "secure_chat")  # off

    assert fresh_db.get_user(1).secure_chat is False
    assert fresh_db.get_user(2).secure_chat is False
    assert any("deactivated" in m["text"] for m in ctx.bot.sent)


def test_secure_chat_refused_without_active_chat(fresh_db):
    register(fresh_db, 1)
    query, _ = press(1, "secure_chat")
    assert query.answers[-1]["show_alert"] is True
    assert query.edits == []


def test_secure_chat_resets_on_new_match_and_end_chat(fresh_db):
    _paired(fresh_db)
    fresh_db.set_secure_chat(1, True)
    assert fresh_db.get_user(1).secure_chat is True

    fresh_db.end_chat(1)
    assert fresh_db.get_user(1).secure_chat is False
    assert fresh_db.get_user(2).secure_chat is False

    fresh_db.pair_users(1, 2)
    assert fresh_db.get_user(1).secure_chat is False


def test_relay_sets_protect_content_when_secure(fresh_db):
    _paired(fresh_db)
    ctx = FakeContext()

    # Secure OFF → protect_content False
    update = FakeUpdate(1, message=FakeMessage(text="hello"))
    asyncio.run(bot.relay_message(update, ctx))
    assert ctx.bot.sent[-1]["protect_content"] is False

    # Secure ON → protect_content True
    fresh_db.set_secure_chat(1, True)
    update2 = FakeUpdate(1, message=FakeMessage(text="secret"))
    asyncio.run(bot.relay_message(update2, ctx))
    assert ctx.bot.sent[-1]["protect_content"] is True


def test_chat_keyboard_secure_label_changes():
    off = [b.text for row in bot.chat_keyboard().inline_keyboard for b in row]
    on = [b.text for row in bot.chat_keyboard(secure=True).inline_keyboard for b in row]
    assert any("Secure Chat" in t for t in off)
    assert any("ON" in t for t in on)


def test_pview_without_active_chat_is_refused(fresh_db):
    register(fresh_db, 1)
    query, _ = press(1, "pview")
    assert query.answers[-1]["show_alert"] is True
    assert query.edits == []


def test_pback_without_active_chat_returns_to_menu(fresh_db):
    register(fresh_db, 1)
    query, _ = press(1, "pback")
    assert "Main Menu" in query.edits[-1]["text"]


def test_back_without_a_list_returns_to_menu(fresh_db):
    register(fresh_db, 1)
    query, _ = press(1, "back_list")
    assert "Main Menu" in query.edits[-1]["text"]


# ── 🚩 Report button on profile cards ───────────────────────────

def test_report_button_from_profile_keyboard_works(fresh_db):
    target = 300
    register(fresh_db, target, gender=Gender.FEMALE)
    markup = bot.profile_view_keyboard(target, liked=False)
    report_btn = next(b for b in _buttons(markup) if "Report" in b.text)

    query, _ = press(1, report_btn.callback_data)
    assert "Report submitted" in query.edits[-1]["text"]


def test_report_from_keyboard_bans_at_threshold(fresh_db):
    from database import BAN_REPORT_THRESHOLD

    target = 300
    register(fresh_db, target, gender=Gender.FEMALE)
    report_btn = next(
        b for b in _buttons(bot.profile_view_keyboard(target, liked=False))
        if "Report" in b.text
    )
    for i in range(BAN_REPORT_THRESHOLD):
        reporter = 400 + i
        register(fresh_db, reporter)
        press(reporter, report_btn.callback_data)
    assert fresh_db.get_user(target).banned is True


def test_stale_callback_points_back_to_menu(fresh_db):
    register(fresh_db, 1)
    query, context = press(1, "button_from_an_old_message")
    assert any("expired" in m["text"] for m in context.bot.sent)


# -- Force-join membership cache ----------------------------------

def test_channel_membership_is_cached_and_joined_check_is_fresh(
    fresh_db, monkeypatch
):
    _enable_force_join(monkeypatch)
    register(fresh_db, 1)

    context = FakeContext()
    context.bot.member_status = "member"
    assert run(bot.is_channel_member(context, 1)) is True

    # positive answers stay cached for a short while (no extra API calls)
    context.bot.member_status = "left"
    assert run(bot.is_channel_member(context, 1)) is True

    # ...but "✅ I've Joined" always bypasses the cache and re-checks
    query, _ = press(1, "joined_check", context)
    assert "haven't joined" in query.answers[-1]["text"]

    # fresh membership flips the same button back to the welcome menu
    context.bot.member_status = "member"
    query, _ = press(1, "joined_check", context)
    assert "Welcome" in query.answers[-1]["text"]
