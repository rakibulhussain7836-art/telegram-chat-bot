"""
Telegram Random Chat Bot — Main Bot Logic

Commands:
  /start      — Register & show main menu (supports referral codes)
  /newchat    — Start a random anonymous chat
  /search     — Choose who to search for (Random / Guy / Girl)
  /stop       — End current chat
  /profile    — View your profile
  /credit     — Coin balance, referral link & coin shop
  /vip        — Upgrade to VIP
  /link       — Your personal invite link
  /link_anon  — Your anonymous chat link
  /report     — Report your current chat partner
  /help       — Show help

Coins: chatting with anyone is free, searching for a Girl costs coins.
Supports: text, photos, stickers, voice, video, documents, GIFs
"""

import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

from telegram import Update, LabeledPrice, BotCommand
from telegram.error import BadRequest
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    ContextTypes,
    filters,
)

from database import (
    db,
    Gender,
    ChatState,
    STARTING_COINS,
    REFERRAL_REWARD,
    REFERRED_BONUS,
    GIRL_SEARCH_COST,
    CHAT_REQUEST_COST,
    CHAT_REQUEST_TTL,
    NEARBY_RADIUS_KM,
    BROWSE_PAGE_SIZE,
)
from keyboards import (
    gender_keyboard,
    preference_keyboard,
    country_keyboard,
    main_menu_keyboard,
    main_reply_keyboard,
    settings_keyboard,
    chat_keyboard,
    searching_keyboard,
    search_choice_keyboard,
    profile_keyboard,
    back_to_profile_keyboard,
    credit_keyboard,
    back_to_credit_keyboard,
    user_list_keyboard,
    share_location_keyboard,
    profile_view_keyboard,
    request_keyboard,
    view_request_keyboard,
    viewed_by_keyboard,
    browse_keyboard,
    swipe_keyboard,
    vip_keyboard,
    verify_keyboard,
    NEW_CHAT_LABEL,
    BROWSE_LABEL,
    NEARBY_LABEL,
)

load_dotenv()
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
# Telegram user ID of the admin (you) — reviews verification photos.
_admin = os.getenv("ADMIN_ID", "")
ADMIN_ID = int(_admin) if _admin.strip().isdigit() else None

# Shows up in Telegram's ☰ Menu, like the reference bot.
BOT_COMMANDS = [
    BotCommand("start", "🏠 Open main menu"),
    BotCommand("profile", "👤 View your profile"),
    BotCommand("newchat", "💬 Start new chat"),
    BotCommand("search", "🔍 Choose who to search for"),
    BotCommand("browse", "🎉 Browse people"),
    BotCommand("stop", "🛑 End the current chat"),
    BotCommand("help", "❓ How it works"),
    BotCommand("link", "🔗 Invite & earn coins"),
    BotCommand("credit", "💰 Check your coins or buy more"),
    BotCommand("link_anon", "👀 Get your anonymous Chat link"),
    BotCommand("vip", "🔥 Upgrade to VIP"),
]


# ═══════════════════════════════════════════════════════════════════
#  MESSAGES / TEMPLATES
# ═══════════════════════════════════════════════════════════════════

WELCOME_MSG = """
❤️ **Welcome to Random Chat Bot!**

Tap «🎲 Random Search» and start chatting now.
🎁 You'll also receive **{free} 🪙** free Coins!

Let's get you set up. First, select your **gender**:
"""

HELP_MSG = """
❓ **How it works**

/start — 🏠 Open main menu
/profile — 👤 View your profile
/newchat — 💬 Start new chat
/search — 🔍 Choose who to search for
/help — ❓ How it works
/link — 🔗 Invite & earn coins
/credit — 💰 Check your coins or buy more
/link_anon — 👀 Get your anonymous Chat link
/vip — 🔥 Upgrade to VIP
/stop — 🛑 End the current conversation

**During a chat:**
• Send any message — it's forwarded anonymously
• Supports: text, photos, stickers, voice, video, GIFs
• Press ⏭️ **Next** to find a new partner
• Press 🛑 **End** to stop chatting
• Press ❤️ **Like** to like your partner's profile
• Press 🚩 **Report** to report your partner

**Discover people:**
• 🎉 **Browse People** — see who is around right now
• 🧭 **Nearby People** — share your location and see people around you
• 🔎 **Find by ID** — search anyone with their 6-digit ID (see yours in /profile)
• 📨 **Chat Request** ({request_cost} 🪙) — they accept within two minutes
• ❤️ Like / 💔 Unlike profiles from the profile view
• ➕ Add to Contacts while chatting — see them in 📇 My Contacts

**Profile:**
• Set your **name, age, city** and 📷 a profile photo
• 🪩 Get Verified — send a photo, an admin reviews it

**Coins:**
• Chatting with anyone is **free**
• Searching for a 👩 **Girl** costs **{cost} 🪙 per search**
• 👑 **VIP** members search for Girls for free
• Earn Coins by inviting friends with /link
• Buy Coins with Telegram Stars via /credit
"""

PROFILE_TEMPLATE = """
{badge} **{name}**
Age: {age} • City: {city}

👁 {online}
ID: `{public_id}`

❤️ {likes} likes
🪙 {coins} Coins
🌍 Country: {country}
🔹 Looking for: {preference}
🔹 Total chats: {total_chats}
📇 Contacts: {contacts}
👥 Referrals: {referrals}
🪩 {verified}
"""

SEARCH_CHOICE_TEXT = """
👫 **Choose who you want to chat with** 👇

🎲 **Random (Free)**
🕺 **Chat With Guy (Free)**
💃 **Chat With Girl ({cost} 🪙 per search)**

💡 Talking to everyone is free — only searching for Girls costs Coins.
"""

AGE_ASK_TEXT = """
🎂 **How old are you?**

Send your age as a number (10–99).
"""

CITY_ASK_TEXT = """
🏙 **Which city are you in?**

Send your city name below.
"""

ALL_SET_TEXT = """
🎉 **You're all set!**

Use the buttons below to find a partner, browse people or open the menu.
"""


def credit_text(user) -> str:
    return (
        f"💰 Your current Coins: **{user.coins}**\n"
        f"{'─' * 24}\n\n"
        f"❓ **How can I get Coin?**\n\n"
        f"1️⃣ **Invite friends (Free)**\n"
        f"Share your personal invite link ⚡ (/link) with friends and earn "
        f"**{REFERRAL_REWARD} Coin** for each referral.\n\n"
        f"2️⃣ **Buy Coin**\n"
        f"Choose one of the plans below 👇\n\n"
        f"💡 *Chatting with anyone is free — searching for a 👩 Girl costs "
        f"{GIRL_SEARCH_COST} 🪙 per search.*\n"
        f"🎁 New accounts start with **{STARTING_COINS} free Coins**."
    )


VIP_PLAN = (6200, 740)  # (coins, stars) — the VIP pack sold via /vip


def vip_text(user) -> str:
    status = "👑 You're a VIP already — thank you!" if user.vip else \
        "🔥 **Upgrade to VIP**"
    return (
        f"{status}\n\n"
        f"👑 **VIP benefits**\n"
        f"• 👩 Girl searches are **free** (everyone else pays "
        f"{GIRL_SEARCH_COST} 🪙 each)\n"
        f"• 👑 VIP badge on your profile card and in every match\n"
        f"• 🔥 VIP label next to your name in lists\n\n"
        f"👑 **{VIP_PLAN[0]} Coins** for **⭐{VIP_PLAN[1]}**\n"
        f"💡 Buy it from the button below — paid securely with Telegram Stars."
    )


# ═══════════════════════════════════════════════════════════════════
#  HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

def format_gender(g):
    if g == Gender.MALE:
        return "👨 Male"
    elif g == Gender.FEMALE:
        return "👩 Female"
    return "Not set"


def gender_emoji(g) -> str:
    if g == Gender.MALE:
        return "👦"
    if g == Gender.FEMALE:
        return "👧"
    return "🧑"


def format_state(s):
    return {
        ChatState.IDLE: "🟢 Online",
        ChatState.SEARCHING: "🔍 Searching...",
        ChatState.CHATTING: "💬 In Chat",
    }.get(s, "Unknown")


def format_online(user) -> str:
    """👁 Online status line shown on profile cards."""
    if user.state == ChatState.CHATTING:
        return "👁 Online (Chatting🗣)"
    if user.state == ChatState.SEARCHING:
        return "👁 Online (Searching🔍)"
    return "👁 Online"


def display_name(user) -> str:
    if user.name:
        return user.name
    if user.username:
        return f"@{user.username}"
    return "Stranger"


async def notify_partner_found(context, user_id, partner_id):
    """Send 'partner found' notifications to both users."""
    user = db.get_user(user_id)
    partner = db.get_user(partner_id)

    for u, p in [(user, partner), (partner, user)]:
        partner_info = (
            f"🎉 **Partner found!**\n\n"
            f"{gender_emoji(p.gender)} **{display_name(p)}**"
            f"{f', {p.age}' if p.age else ''}\n"
            f"🌍 {p.city or p.country or 'Unknown'}\n"
            f"👁 {format_online(p)}\n"
            f"🪩 {verified_label(p)}\n"
            f"🆔 ID: `{p.public_id}`\n\n"
            f"Say hi! Type your message below.\n"
            f"Use /stop or the buttons to end the chat."
        )
        await context.bot.send_message(
            chat_id=u.user_id,
            text=partner_info,
            parse_mode="Markdown",
            reply_markup=chat_keyboard(),
        )
        # Send the partner's profile photo (they never see their own)
        if p.photo_file_id:
            try:
                await context.bot.send_photo(
                    chat_id=u.user_id,
                    photo=p.photo_file_id,
                    caption="📷 Partner's profile photo",
                )
            except Exception as e:
                logger.warning(f"Failed to send partner photo to {u.user_id}: {e}")


async def safe_edit(query, text, parse_mode=None, reply_markup=None):
    """Edit a message (or its caption when it carries a photo)."""
    message = getattr(query, "message", None)
    has_photo = bool(message is not None and getattr(message, "photo", None))
    try:
        if has_photo:
            await query.edit_message_caption(
                caption=text, parse_mode=parse_mode, reply_markup=reply_markup
            )
        else:
            await query.edit_message_text(
                text, parse_mode=parse_mode, reply_markup=reply_markup
            )
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


async def get_referral_link(context, user_id: int) -> str:
    me = await context.bot.get_me()
    return f"https://t.me/{me.username}?start={user_id}"


def build_profile_text(user) -> str:
    return PROFILE_TEMPLATE.format(
        badge="👑" if user.vip else gender_emoji(user.gender),
        name=display_name(user),
        age=user.age if user.age else "—",
        city=user.city or (user.country or "—"),
        online=format_online(user),
        public_id=user.public_id,
        likes=user.likes,
        coins=user.coins,
        country=user.country or "Not set",
        preference=format_gender(user.preferred_gender)
        if user.preferred_gender != Gender.ANY
        else "🌍 Anyone",
        total_chats=user.total_chats,
        contacts=len(user.contacts),
        referrals=user.referral_count,
        verified=verified_label(user),
    )


def verified_label(user) -> str:
    """✅ badge shown next to verified accounts."""
    if not user.verified:
        return "❌ Not verified"
    gender = user.verified_gender or user.gender
    if gender == Gender.MALE:
        return "✅ Verified Boy"
    if gender == Gender.FEMALE:
        return "✅ Verified Girl"
    return "✅ Verified"


def build_user_card(target, viewer_id: int) -> str:
    """Profile card for someone else's account (ID search / Nearby / Browse)."""
    lines = [
        f"{gender_emoji(target.gender)} **{display_name(target)}**"
        f"{f', {target.age}' if target.age else ''}",
        f"📍 {target.city or target.country or 'Not set'}",
        "",
        f"👁 {format_online(target)}",
        f"🆔 ID: `{target.public_id}`",
        "",
        f"❤️ {target.likes} likes",
        f"🔹 **Gender:** {format_gender(target.gender)}",
        f"🪩 {verified_label(target)}",
    ]
    if target.vip:
        lines.append("👑 VIP member")
    distance = db.distance_km(viewer_id, target.user_id)
    if distance is not None:
        lines.append(f"📍 Distance: {distance:.0f} km away")
    lines += [
        "",
        f"📨 Chat request costs **{CHAT_REQUEST_COST} 🪙** "
        f"(answered within {CHAT_REQUEST_TTL // 60} min)",
    ]
    return "\n".join(lines)


def _remember_list_message(context, query) -> None:
    """Remember which message holds a list so Back can refresh it."""
    message = getattr(query, "message", None)
    message_id = getattr(message, "message_id", None)
    if message_id:
        context.user_data["list_message_id"] = message_id


async def show_user_card(query, context, viewer_id: int, target) -> None:
    """
    Open someone's profile. When they have a photo the card is sent as a
    photo message (like the reference bot); otherwise the current message
    is edited in place.
    """
    liked = viewer_id in target.liked_by
    notify = db.get_user(viewer_id).notify_on_end
    markup = profile_view_keyboard(target.user_id, liked, notify)
    text = build_user_card(target, viewer_id)

    if target.photo_file_id:
        _remember_list_message(context, query)
        try:
            await context.bot.send_photo(
                chat_id=viewer_id,
                photo=target.photo_file_id,
                caption=text,
                parse_mode="Markdown",
                reply_markup=markup,
            )
            return
        except Exception as e:
            logger.warning(f"Failed to send profile photo card: {e}")

    await safe_edit(query, text, parse_mode="Markdown", reply_markup=markup)


async def reply_profile_card(message, viewer_id: int, target) -> None:
    """Same card, but as a reply (text input flows such as Find by ID)."""
    markup = profile_view_keyboard(
        target.user_id,
        viewer_id in target.liked_by,
        db.get_user(viewer_id).notify_on_end,
    )
    text = build_user_card(target, viewer_id)
    if target.photo_file_id and hasattr(message, "reply_photo"):
        try:
            await message.reply_photo(
                photo=target.photo_file_id,
                caption=text,
                parse_mode="Markdown",
                reply_markup=markup,
            )
            return
        except Exception as e:
            logger.warning(f"Failed to reply with profile photo: {e}")
    await message.reply_text(
        text, parse_mode="Markdown", reply_markup=markup
    )


def _plain_label(user) -> str:
    return (
        f"{gender_emoji(user.gender)} {display_name(user)}"
        f"{f', {user.age}' if user.age else ''}"
    )


def _nearby_pairs(viewer_id: int) -> list:
    pairs = []
    for target, dist in db.nearby_users(viewer_id):
        pairs.append((
            f"{_plain_label(target)} • 📍 {dist:.0f} km",
            target,
        ))
    return pairs


def _pairs_from_ids(viewer_id: int, ids, kind: str) -> list:
    pairs = []
    for uid in ids:
        user = db.get_user(uid)
        if not user:
            continue
        if kind == "nearby":
            dist = db.distance_km(viewer_id, uid)
            prefix = f"📍 {dist:.0f} km • " if dist is not None else "📍 "
            pairs.append((f"{prefix}{_plain_label(user)}", user))
        else:
            pairs.append((_plain_label(user), user))
    return pairs


def _list_text(title: str, pairs) -> str:
    if not pairs:
        return f"{title}\n\nNo one here right now."
    return f"{title}\n\n👥 {len(pairs)} found — tap one to open their profile:"


def _browse_entry(target) -> str:
    """One 🎉 Browse People entry, formatted like the reference bot."""
    place = ", ".join(p for p in (target.country, target.city) if p) or "Not set"
    return (
        f"{gender_emoji(target.gender)} **{display_name(target)}**"
        f"{f', {target.age}' if target.age else ''} • `{target.public_id}`\n"
        f"📍 {place}\n"
        f"👀 {format_online(target)}\n"
        f"{'〰️' * 8}"
    )


def _browse_text(users, total: int) -> str:
    if not users:
        return "🎉 **Browse People**\n\nNo one else is here yet — check back soon!"
    header = f"🎉 **People online** ({total})"
    body = "\n\n".join(_browse_entry(u) for u in users)
    return f"{header}\n\n{body}\n\nShowing 1–{len(users)} of {total}."


def _browse_state(context, user_id: int):
    """(text, markup) for the current Browse People page."""
    ids = context.user_data.get("browse_ids", [])
    users = [u for u in (db.get_user(i) for i in ids) if u]
    total = context.user_data.get("browse_total", len(users))
    has_more = len(users) < total
    pairs = [(_plain_label(u), u) for u in users]
    return _browse_text(users, total), browse_keyboard(has_more, pairs)


async def _render_swipe(query, context, viewer_id: int, index: int) -> None:
    """✨ View Profiles by Swiping — one card at a time."""
    ids = context.user_data.get("swipe_ids", [])
    target = db.get_user(ids[index])
    if not target:
        await query.answer("That account no longer exists.", show_alert=True)
        return
    text = f"{_browse_entry(target)}\n\nProfile {index + 1} of {len(ids)}"
    await safe_edit(
        query,
        text,
        parse_mode="Markdown",
        reply_markup=swipe_keyboard(
            index, len(ids), target.user_id, viewer_id in target.liked_by
        ),
    )


async def notify_profile_view(context, viewer_id: int, target) -> None:
    """🧖 "A guy/girl just viewed your profile" toast."""
    viewer = db.get_user(viewer_id)
    if not viewer:
        return
    kind = {Gender.MALE: "Guy", Gender.FEMALE: "Girl"}.get(viewer.gender, "Someone")
    try:
        await context.bot.send_message(
            chat_id=target.user_id,
            text=f"🧖 A {kind} just viewed your profile 👀🔥",
            reply_markup=viewed_by_keyboard(viewer_id),
        )
    except Exception as e:
        logger.warning(f"Failed to send view alert to {target.user_id}: {e}")


async def _ping_chat_end(context, user_id: int, partner_id) -> None:
    """Honour the 🔔 "notify me when chat ends" toggle on both sides."""
    for uid in (user_id, partner_id):
        if not uid:
            continue
        target = db.get_user(uid)
        if target and target.notify_on_end:
            db.set_notify_end(uid, False)
            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text="🔔 Your chat has ended.",
                    reply_markup=main_menu_keyboard(),
                )
            except Exception as e:
                logger.warning(f"Failed to send chat-end notice to {uid}: {e}")


async def close_chat(context, user_id: int, leaver_notice: str = "👋 You left the chat."):
    """
    End a chat for user_id, tell both sides and honour the
    🔔 "notify me when chat ends" toggle.
    """
    partner_id = db.end_chat(user_id)
    await context.bot.send_message(
        chat_id=user_id, text=leaver_notice, reply_markup=main_menu_keyboard()
    )
    if partner_id:
        await context.bot.send_message(
            chat_id=partner_id,
            text="⚠️ Your partner has left the chat.",
            reply_markup=main_menu_keyboard(),
        )
    await _ping_chat_end(context, user_id, partner_id)


async def begin_search(context, user_id: int, search_pref: Gender):
    """
    Start a search with the given per-search filter.
    Charges coins when searching for a Girl (VIP members search free).
    Returns (text, reply_markup, parse_mode).
    """
    user = db.get_user(user_id)
    if not user:
        return "Please /start first.", None, None

    if user.banned:
        return "🚫 Your account is restricted.", main_menu_keyboard(), None

    if not user.gender or not user.country:
        return (
            "⚠️ Please complete your profile first (gender & country).\n"
            "Use /start to set up.",
            None,
            None,
        )

    if user.state == ChatState.CHATTING:
        return "You're already in a chat! Use /stop to leave first.", chat_keyboard(), None

    if user.state == ChatState.SEARCHING:
        return "⏳ You're already searching for a partner...", searching_keyboard(), None

    charged = False
    if search_pref == Gender.FEMALE and not user.vip:
        if not db.spend_coins(user_id, GIRL_SEARCH_COST):
            return (
                f"🪙 **Not enough Coins!**\n\n"
                f"Searching for a 👩 Girl costs **{GIRL_SEARCH_COST} 🪙 per search**.\n"
                f"Invite friends (/link) or buy Coins (/credit) to earn more.",
                credit_keyboard(),
                "Markdown",
            )
        charged = True

    db.add_to_queue(user_id, search_pref=search_pref)
    match_id = db.find_match(user_id)

    if match_id:
        db.pair_users(user_id, match_id)
        await notify_partner_found(context, user_id, match_id)
        text = "🎉 Partner found! Connecting..."
        if charged:
            balance = db.get_user(user_id).coins
            text += f"\n🪙 -{GIRL_SEARCH_COST} | Balance: {balance}"
        return text, None, None

    text = (
        "🔍 **Searching for a partner...**\n\n"
        f"👥 {db.searching_count} people in queue\n"
        "Please wait, you'll be connected soon!"
    )
    if charged:
        balance = db.get_user(user_id).coins
        text += f"\n\n🪙 -{GIRL_SEARCH_COST} (Girl search) | Balance: {balance}"
    return text, searching_keyboard(), "Markdown"


async def process_report(context, reporter_id: int) -> tuple[str, bool]:
    """
    Report the reporter's current partner, block them from future matches
    and end the chat. Returns (message, was_in_chat).
    """
    user = db.get_user(reporter_id)
    if not user or user.state != ChatState.CHATTING or not user.partner_id:
        return "⚠️ There is no active chat to report.", False

    partner_id = user.partner_id
    banned_now = db.add_report(reporter_id, partner_id)
    await close_chat(context, reporter_id, leaver_notice="👋 You left the chat.")

    if banned_now:
        db.remove_from_queue(partner_id)
        try:
            await context.bot.send_message(
                chat_id=partner_id,
                text="🚫 Your account has been restricted because of multiple "
                     "reports from other users.",
                reply_markup=main_menu_keyboard(),
            )
        except Exception as e:
            logger.warning(f"Failed to notify banned user {partner_id}: {e}")

    return (
        "✅ **Report submitted.** This user won't be matched with you again.",
        True,
    )


# ═══════════════════════════════════════════════════════════════════
#  COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    first_name = getattr(update.effective_user, "first_name", None)
    ref_code = context.args[0] if context.args else None
    existing = db.get_user(user_id)
    is_new = existing is None

    # Deep link to someone's profile: /start chat_<public_id>
    if ref_code and ref_code.startswith("chat_"):
        target = db.resolve_id(ref_code[len("chat_"):])
        db.register_user(user_id, username, name=first_name)
        if target and target.user_id != user_id:
            db.record_view(user_id, target.user_id)
            await reply_profile_card(update.message, user_id, target)
            return

    # End any existing chat
    partner_id = db.end_chat(user_id)
    if partner_id:
        await context.bot.send_message(
            chat_id=partner_id,
            text="⚠️ Your partner has left the chat.",
            reply_markup=main_menu_keyboard(),
        )

    db.remove_from_queue(user_id)
    user = db.register_user(user_id, username, name=first_name)

    # Returning users just get the menu (like the reference bot)
    if not is_new and user.gender and user.country:
        await update.message.reply_text(
            "🏠 **Main Menu**",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
        await update.message.reply_text(
            "👇 Use the buttons below anytime.",
            reply_markup=main_reply_keyboard(),
        )
        return

    welcome = WELCOME_MSG.format(free=STARTING_COINS)

    # Referral deep link: /start <referrer_id>
    if is_new and ref_code and ref_code.isdigit():
        referrer_id = int(ref_code)
        gains = db.apply_referral(referrer_id, user_id)
        if gains:
            referrer_gain, new_user_gain = gains
            bonus_line = (
                f"🎁 **Referral bonus!** You got **+{new_user_gain} 🪙** "
                f"for joining via a friend's link.\n\n"
            )
            welcome = welcome.replace(
                "Let's get you set up.", bonus_line + "Let's get you set up."
            )
            referrer = db.get_user(referrer_id)
            try:
                await context.bot.send_message(
                    chat_id=referrer_id,
                    text=(
                        f"🎉 **New referral!**\n\n"
                        f"A friend joined with your invite link.\n"
                        f"🪙 **+{referrer_gain}** Coins added!\n"
                        f"💰 Balance: **{referrer.coins}** Coins"
                    ),
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.warning(f"Failed to notify referrer {referrer_id}: {e}")

    await update.message.reply_text(
        welcome,
        parse_mode="Markdown",
        reply_markup=gender_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        HELP_MSG.format(cost=GIRL_SEARCH_COST, request_cost=CHAT_REQUEST_COST),
        parse_mode="Markdown",
    )


async def find_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user:
        await update.message.reply_text("Please /start first to set up your profile.")
        return

    if user.banned:
        await update.message.reply_text("🚫 Your account is restricted.")
        return

    if not user.gender or not user.country:
        await update.message.reply_text(
            "⚠️ Please complete your profile first (gender & country).\nUse /start to set up."
        )
        return

    if user.state == ChatState.CHATTING:
        await update.message.reply_text(
            "You're already in a chat! Use /stop to leave first.",
            reply_markup=chat_keyboard(),
        )
        return

    if user.state == ChatState.SEARCHING:
        await update.message.reply_text(
            "⏳ You're already searching for a partner...",
            reply_markup=searching_keyboard(),
        )
        return

    await update.message.reply_text(
        SEARCH_CHOICE_TEXT.format(cost=GIRL_SEARCH_COST),
        parse_mode="Markdown",
        reply_markup=search_choice_keyboard(),
    )


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user:
        return

    if user.state == ChatState.SEARCHING:
        db.remove_from_queue(user_id)
        await update.message.reply_text(
            "❌ Search cancelled.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if user.state == ChatState.CHATTING:
        await close_chat(context, user_id, leaver_notice="👋 You left the chat.")
        return

    await update.message.reply_text(
        "You're not in a chat right now.",
        reply_markup=main_menu_keyboard(),
    )


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user:
        await update.message.reply_text("Please /start first.")
        return

    await update.message.reply_text(
        build_profile_text(user),
        parse_mode="Markdown",
        reply_markup=profile_keyboard(),
    )


async def credit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user:
        await update.message.reply_text("Please /start first.")
        return

    await update.message.reply_text(
        credit_text(user), parse_mode="Markdown", reply_markup=credit_keyboard()
    )


async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user:
        await update.message.reply_text("Please /start first.")
        return

    link = await get_referral_link(context, user_id)
    await update.message.reply_text(
        f"⚡ **Your personal invite link:**\n`{link}`\n\n"
        f"🎁 You earn **{REFERRAL_REWARD} 🪙** for every friend who joins "
        f"(they get **+{REFERRED_BONUS} 🪙** too).\n\n"
        f"👥 Referrals: **{user.referral_count}**\n"
        f"🪙 Earned from referrals: **{user.referral_earned}**\n"
        f"💰 Balance: **{user.coins} 🪙**",
        parse_mode="Markdown",
    )


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.get_user(user_id):
        await update.message.reply_text("Please /start first.")
        return

    text, _ = await process_report(context, user_id)
    await update.message.reply_text(
        text, parse_mode="Markdown", reply_markup=main_menu_keyboard()
    )


async def newchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """💬 Start new chat — jumps straight into a random search."""
    user_id = update.effective_user.id
    if not db.get_user(user_id):
        await update.message.reply_text("Please /start first.")
        return
    text, markup, mode = await begin_search(context, user_id, Gender.ANY)
    await update.message.reply_text(text, parse_mode=mode, reply_markup=markup)


async def browse_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🎉 Browse People — paginated list of everyone around."""
    user_id = update.effective_user.id
    if not db.get_user(user_id):
        await update.message.reply_text("Please /start first.")
        return
    page, total = db.browse_users(user_id, 0, BROWSE_PAGE_SIZE)
    context.user_data["browse_ids"] = [u.user_id for u in page]
    context.user_data["browse_offset"] = len(page)
    context.user_data["browse_total"] = total
    context.user_data["list_ids"] = context.user_data["browse_ids"]
    context.user_data["list_title"] = "🎉 People online"
    context.user_data["list_kind"] = "browse"
    await update.message.reply_text(
        _browse_text(page, total),
        parse_mode="Markdown",
        reply_markup=browse_keyboard(
            len(page) < total, [(_plain_label(u), u) for u in page]
        ),
    )


async def vip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if not user:
        await update.message.reply_text("Please /start first.")
        return
    await update.message.reply_text(
        vip_text(user), parse_mode="Markdown", reply_markup=vip_keyboard()
    )


async def link_anon_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if not user:
        await update.message.reply_text("Please /start first.")
        return
    me = await context.bot.get_me()
    link = f"https://t.me/{me.username}?start=chat_{user.public_id}"
    await update.message.reply_text(
        f"👀 **Your anonymous Chat link:**\n`{link}`\n\n"
        f"Anyone who opens it lands straight on your profile card — they can "
        f"like you, send a 💬 Direct Message or a 📨 Chat Request.",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


# ═══════════════════════════════════════════════════════════════════
#  ADMIN — verification review (restricted to ADMIN_ID)
# ═══════════════════════════════════════════════════════════════════

def _is_admin(update: Update) -> bool:
    return ADMIN_ID is not None and update.effective_user.id == ADMIN_ID


async def verifylist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    pending = db.pending_verifications_list()
    if not pending:
        await update.message.reply_text("🪩 No pending verification requests.")
        return

    lines = ["🪩 **Pending verifications**", ""]
    for uid, info in pending:
        target = db.get_user(uid)
        lines.append(
            f"• `{uid}` (ID `{target.public_id if target else '?'}`) "
            f"@{target.username if target and target.username else '-'} "
            f"— claims **{info['gender']}**"
        )
    lines += [
        "",
        "Approve: `/verifyok <id>`   Reject: `/verifyno <id>`",
        "_(user ID or the 6-digit profile ID)_",
    ]
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    for uid, info in pending:
        try:
            await context.bot.send_photo(
                chat_id=update.effective_user.id,
                photo=info["file_id"],
                caption=f"🪩 Evidence submitted by {uid}",
            )
        except Exception as e:
            logger.warning(f"Failed to send verification photo for {uid}: {e}")


async def verifyok_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /verifyok <user_id or 6-digit ID>")
        return
    target = db.resolve_id(context.args[0])
    if not target:
        await update.message.reply_text("No such user.")
        return
    user = db.approve_verification(target.user_id)
    if not user:
        await update.message.reply_text("Nothing pending for that user.")
        return
    await update.message.reply_text(
        f"✅ Verified {user.user_id} → {verified_label(user)}"
    )
    try:
        await context.bot.send_message(
            chat_id=user.user_id,
            text=(
                f"🪩 **Verification approved!**\n\n"
                f"{verified_label(user)} — your badge is now live on your "
                f"profile and in every match."
            ),
            parse_mode="Markdown",
            reply_markup=profile_keyboard(),
        )
    except Exception as e:
        logger.warning(f"Failed to notify verified user {user.user_id}: {e}")


async def verifyno_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /verifyno <user_id or 6-digit ID>")
        return
    target = db.resolve_id(context.args[0])
    if not target:
        await update.message.reply_text("No such user.")
        return
    if not db.reject_verification(target.user_id):
        await update.message.reply_text("Nothing pending for that user.")
        return
    await update.message.reply_text(f"❌ Rejected {target.user_id}")
    try:
        await context.bot.send_message(
            chat_id=target.user_id,
            text=(
                "🪩 **Verification rejected**\n\n"
                "The photo didn't pass review. You can try again from "
                "⚙️ Settings → 🪩 Get Verified."
            ),
            parse_mode="Markdown",
            reply_markup=settings_keyboard(),
        )
    except Exception as e:
        logger.warning(f"Failed to notify rejected user {target.user_id}: {e}")


# ═══════════════════════════════════════════════════════════════════
#  CALLBACK QUERY HANDLERS (inline buttons)
# ═══════════════════════════════════════════════════════════════════

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    user = db.get_user(user_id)
    if not user:
        db.register_user(user_id, query.from_user.username)
        user = db.get_user(user_id)

    # ── Like partner (answered with a toast instead) ─────────
    if data == "like_partner":
        if user.state != ChatState.CHATTING or not user.partner_id:
            await query.answer("⚠️ You're not in a chat right now.", show_alert=True)
            return
        partner_id = user.partner_id
        is_new, total = db.add_like(user_id, partner_id)
        if not is_new:
            await query.answer("You already liked this profile ❤️")
            return
        await query.answer("❤️ Liked!")
        try:
            await context.bot.send_message(
                chat_id=partner_id,
                text=f"❤️ Someone liked your profile! Total likes: {total}",
            )
        except Exception as e:
            logger.warning(f"Failed to notify like to {partner_id}: {e}")
        return

    await query.answer()

    # ── Gender selection ────────────────────────────────────
    if data.startswith("gender_"):
        gender = Gender.MALE if data == "gender_male" else Gender.FEMALE
        db.update_gender(user_id, gender)
        await safe_edit(
            query,
            f"✅ Gender set to **{format_gender(gender)}**\n\n"
            "Now select your **country**:",
            parse_mode="Markdown",
            reply_markup=country_keyboard(),
        )

    # ── Country selection ───────────────────────────────────
    elif data.startswith("country_"):
        country_code = data.replace("country_", "")
        if country_code == "other":
            context.user_data["awaiting_country"] = True
            await safe_edit(
                query,
                "🌐 Type your **country name** below:",
                parse_mode="Markdown",
            )
        else:
            db.update_country(user_id, country_code)
            await safe_edit(
                query,
                f"✅ Country set to **{country_code}**\n\n"
                "Who would you like to chat with?",
                parse_mode="Markdown",
                reply_markup=preference_keyboard(),
            )

    # ── Gender preference ───────────────────────────────────
    elif data.startswith("pref_"):
        pref_map = {"pref_male": Gender.MALE, "pref_female": Gender.FEMALE, "pref_any": Gender.ANY}
        pref = pref_map.get(data, Gender.ANY)
        db.update_preferred_gender(user_id, pref)
        label = format_gender(pref) if pref != Gender.ANY else "🌍 Anyone"
        context.user_data["setup_flow"] = True
        context.user_data["awaiting_age"] = True
        await safe_edit(
            query,
            f"✅ You'll be matched with: **{label}**\n\n" + AGE_ASK_TEXT.strip(),
            parse_mode="Markdown",
        )

    # ── Main menu actions ───────────────────────────────────
    elif data == "find_partner":
        if user.banned:
            await safe_edit(query, "🚫 Your account is restricted.")
            return

        if not user.gender or not user.country:
            await safe_edit(
                query, "⚠️ Complete your profile first.\nUse /start to set up."
            )
            return

        if user.state == ChatState.CHATTING:
            await safe_edit(
                query,
                "You're already in a chat! Use /stop to leave first.",
                reply_markup=chat_keyboard(),
            )
            return

        if user.state == ChatState.SEARCHING:
            await safe_edit(
                query,
                "⏳ You're already searching for a partner...",
                reply_markup=searching_keyboard(),
            )
            return

        await safe_edit(
            query,
            SEARCH_CHOICE_TEXT.format(cost=GIRL_SEARCH_COST),
            parse_mode="Markdown",
            reply_markup=search_choice_keyboard(),
        )

    # ── Per-search partner choice ───────────────────────────
    elif data in ("search_random", "search_guy", "search_girl"):
        pref_map = {
            "search_random": Gender.ANY,
            "search_guy": Gender.MALE,
            "search_girl": Gender.FEMALE,
        }
        text, markup, parse_mode = await begin_search(context, user_id, pref_map[data])
        await safe_edit(query, text, parse_mode=parse_mode, reply_markup=markup)

    elif data == "my_profile":
        await safe_edit(
            query, build_profile_text(user), parse_mode="Markdown",
            reply_markup=profile_keyboard(),
        )

    elif data == "stats":
        await safe_edit(
            query,
            f"📊 **Bot Statistics**\n\n"
            f"👥 Registered users: **{db.online_count}**\n"
            f"🔍 Searching now: **{db.searching_count}**\n"
            f"💬 Active chats: **{db.chatting_count}**",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )

    elif data == "settings":
        await safe_edit(
            query,
            "⚙️ **Settings**\n\nWhat would you like to change?",
            parse_mode="Markdown",
            reply_markup=settings_keyboard(),
        )

    elif data == "back_menu":
        await safe_edit(
            query,
            "🏠 **Main Menu**",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )

    # ── Credits / coin shop ─────────────────────────────────
    elif data == "credit_menu":
        await safe_edit(
            query, credit_text(user), parse_mode="Markdown",
            reply_markup=credit_keyboard(),
        )

    elif data == "show_refer":
        link = await get_referral_link(context, user_id)
        await safe_edit(
            query,
            f"🎁 **Refer Friends (Free Coin)**\n\n"
            f"⚡ Your personal invite link:\n`{link}`\n\n"
            f"Share it with friends — you earn **{REFERRAL_REWARD} 🪙** for each "
            f"friend who joins (they get **+{REFERRED_BONUS} 🪙** too).\n\n"
            f"👥 Referrals: **{user.referral_count}**\n"
            f"🪙 Earned: **{user.referral_earned}**\n"
            f"💰 Balance: **{user.coins} 🪙**",
            parse_mode="Markdown",
            reply_markup=back_to_credit_keyboard(),
        )

    elif data.startswith("buy_"):
        try:
            _, stars_s, coins_s = data.split("_")
            stars, coins = int(stars_s), int(coins_s)
        except ValueError:
            await safe_edit(query, "⚠️ Invalid plan. Please try again.",
                            reply_markup=back_to_credit_keyboard())
            return

        try:
            await context.bot.send_invoice(
                chat_id=user_id,
                title=f"{coins} Coins",
                description=f"Get {coins} Coins for Random Chat Bot.",
                payload=f"coin_pack:{user_id}:{coins}",
                provider_token=None,
                currency="XTR",
                prices=[LabeledPrice(label=f"{coins} Coins", amount=stars)],
            )
        except Exception as e:
            logger.error(f"Failed to send invoice: {e}")
            await safe_edit(
                query,
                "⚠️ Could not create the invoice. Please try again later.",
                reply_markup=back_to_credit_keyboard(),
            )
            return

        await safe_edit(
            query,
            f"⬆️ **Payment invoice sent!**\n\n"
            f"Complete the Telegram Stars payment below.\n"
            f"🪙 **{coins} Coins** will be added automatically after payment.",
            parse_mode="Markdown",
            reply_markup=back_to_credit_keyboard(),
        )

    # ── Likes ───────────────────────────────────────────────
    elif data == "view_likers":
        likers = db.likers_of(user_id)
        if not likers:
            text = (
                "❤️ **No likes yet**\n\n"
                "When someone likes your profile, they'll show up here."
            )
        else:
            lines = []
            for liker in likers[:20]:
                label = f"@{liker.username}" if liker.username else f"User {liker.user_id}"
                lines.append(f"• {label}")
            more = f"\n…and {len(likers) - 20} more" if len(likers) > 20 else ""
            text = (
                f"❤️ **People who liked you** ({len(likers)})\n\n"
                + "\n".join(lines)
                + more
                + f"\n\n🔹 Total likes on your profile: **{user.likes}**"
            )
        await safe_edit(
            query, text, parse_mode="Markdown", reply_markup=back_to_profile_keyboard()
        )

    # ── Settings sub-actions ────────────────────────────────
    elif data == "change_gender":
        await safe_edit(
            query,
            "Select your new **gender**:",
            parse_mode="Markdown",
            reply_markup=gender_keyboard(),
        )

    elif data == "change_country":
        await safe_edit(
            query,
            "Select your new **country**:",
            parse_mode="Markdown",
            reply_markup=country_keyboard(),
        )

    elif data == "change_pref":
        await safe_edit(
            query,
            "Who would you like to chat with?",
            parse_mode="Markdown",
            reply_markup=preference_keyboard(),
        )

    elif data == "change_name":
        context.user_data["awaiting_name"] = True
        await safe_edit(
            query,
            "✏️ **Send your new name**\n\nThis is what other people see on "
            "your profile card.",
            parse_mode="Markdown",
        )

    elif data == "change_age":
        context.user_data["awaiting_age"] = True
        await safe_edit(query, AGE_ASK_TEXT.strip(), parse_mode="Markdown")

    elif data == "change_city":
        context.user_data["awaiting_city"] = True
        await safe_edit(query, CITY_ASK_TEXT.strip(), parse_mode="Markdown")

    elif data == "set_photo":
        context.user_data["awaiting_photo"] = True
        await safe_edit(
            query,
            "📷 **Send your profile photo**\n\n"
            "Send a photo now — it will be sent to your partner when you get "
            "matched. Send any other message to cancel.",
            parse_mode="Markdown",
            reply_markup=settings_keyboard(),
        )

    # ── Verification ────────────────────────────────────────
    elif data == "verify_start":
        if user.verified:
            await query.answer(f"Already verified: {verified_label(user)}")
            return
        await safe_edit(
            query,
            "🪩 **Get verified**\n\n"
            "1. Pick what you are\n"
            "2. Send a clear photo of yourself as evidence\n"
            "3. An admin reviews it — you get a ✅ badge on your profile",
            parse_mode="Markdown",
            reply_markup=verify_keyboard(),
        )

    elif data in ("verify_boy", "verify_girl"):
        context.user_data["verify_gender"] = (
            Gender.MALE if data == "verify_boy" else Gender.FEMALE
        )
        context.user_data["awaiting_verify"] = True
        await safe_edit(
            query,
            "🪩 **Send your verification photo**\n\n"
            "Send a photo showing your face now. An admin will review it.\n"
            "Send any other message to cancel.",
            parse_mode="Markdown",
            reply_markup=settings_keyboard(),
        )

    # ── Discovery: Nearby / ID search / Contacts ────────────
    elif data == "nearby":
        if not db.has_location(user_id):
            context.user_data["awaiting_location"] = True
            await safe_edit(
                query,
                f"📍 **Nearby**\n\n"
                f"Share your location to see people within "
                f"{NEARBY_RADIUS_KM} km of you.",
                parse_mode="Markdown",
                reply_markup=share_location_keyboard(),
            )
        else:
            pairs = _nearby_pairs(user_id)
            context.user_data["list_ids"] = [u.user_id for _, u in pairs]
            context.user_data["list_title"] = "📍 People near you"
            context.user_data["list_kind"] = "nearby"
            _remember_list_message(context, query)
            await safe_edit(
                query,
                _list_text("📍 People near you", pairs),
                parse_mode="Markdown",
                reply_markup=user_list_keyboard(pairs),
            )

    elif data == "share_location":
        context.user_data["awaiting_location"] = True
        await safe_edit(
            query,
            "📍 **Send your location**\n\n"
            "Open the attachment menu ➡️ 📍 Location and send it "
            "(live location works too).",
            parse_mode="Markdown",
            reply_markup=share_location_keyboard(),
        )

    elif data == "find_id":
        context.user_data["awaiting_id"] = True
        await safe_edit(
            query,
            "🔎 **Find by ID**\n\n"
            "Type the person's 6-digit ID (they can see it in /profile).",
            parse_mode="Markdown",
        )

    elif data == "contacts":
        users = db.contacts_of(user_id)
        pairs = [(_plain_label(u), u) for u in users]
        context.user_data["list_ids"] = [u.user_id for u in users]
        context.user_data["list_title"] = "📇 My Contacts"
        context.user_data["list_kind"] = "plain"
        await safe_edit(
            query,
            _list_text("📇 **My Contacts**", pairs)
            if pairs
            else "📇 **No contacts yet**\n\nAdd people with **➕ Add to "
                 "Contacts** while you're chatting.",
            parse_mode="Markdown",
            reply_markup=user_list_keyboard(pairs),
        )

    elif data == "back_list":
        ids = context.user_data.get("list_ids", [])
        title = context.user_data.get("list_title", "Results")
        kind = context.user_data.get("list_kind", "plain")

        # A photo card is its own message — drop it and refresh the list.
        message = getattr(query, "message", None)
        if message is not None and getattr(message, "photo", None):
            list_message_id = context.user_data.get("list_message_id")
            try:
                await message.delete()
            except Exception as e:
                logger.warning(f"Failed to delete profile card: {e}")
            if kind == "browse":
                text, markup = _browse_state(context, user_id)
            else:
                pairs = _pairs_from_ids(user_id, ids, kind)
                text = _list_text(title, pairs)
                markup = user_list_keyboard(pairs)
            if list_message_id:
                try:
                    await context.bot.edit_message_text(
                        chat_id=user_id,
                        message_id=list_message_id,
                        text=text,
                        parse_mode="Markdown",
                        reply_markup=markup,
                    )
                    return
                except Exception as e:
                    logger.warning(f"Failed to refresh list message: {e}")
            await context.bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=markup,
            )
            return

        if kind == "browse":
            text, markup = _browse_state(context, user_id)
            await safe_edit(query, text, parse_mode="Markdown", reply_markup=markup)
            return

        pairs = _pairs_from_ids(user_id, ids, kind)
        await safe_edit(
            query, _list_text(title, pairs), parse_mode="Markdown",
            reply_markup=user_list_keyboard(pairs),
        )

    elif data.startswith("view_") and data[5:].isdigit():
        target = db.get_user(int(data[5:]))
        if not target:
            await query.answer("That account no longer exists.", show_alert=True)
            return
        _remember_list_message(context, query)
        await show_user_card(query, context, user_id, target)
        if db.record_view(user_id, target.user_id):
            await notify_profile_view(context, user_id, target)

    # ── Profile card actions ───────────────────────────────
    elif data.startswith("dm_"):
        target = db.get_user(int(data[len("dm_"):]))
        if not target:
            await query.answer("That account no longer exists.", show_alert=True)
            return
        if user.banned or target.banned:
            await query.answer(
                "🚫 Restricted accounts can't start a chat.", show_alert=True
            )
            return
        if target.state != ChatState.IDLE:
            await query.answer(
                "They're busy right now — send a Chat Request instead.",
                show_alert=True,
            )
            return
        if user.state == ChatState.CHATTING:
            await query.answer(
                "You're already in a chat! Use /stop first.", show_alert=True
            )
            return
        if user.state == ChatState.SEARCHING:
            db.remove_from_queue(user_id)
        db.pair_users(user_id, target.user_id)
        await safe_edit(
            query,
            "💬 **Direct chat started! Say hi 👋**",
            parse_mode="Markdown",
            reply_markup=chat_keyboard(),
        )
        await notify_partner_found(context, user_id, target.user_id)

    elif data.startswith("block_"):
        target = db.get_user(int(data[len("block_"):]))
        if not target:
            await query.answer("That account no longer exists.", show_alert=True)
            return
        db.block_user(user_id, target.user_id)
        if user.state == ChatState.CHATTING and user.partner_id == target.user_id:
            await close_chat(
                context,
                user_id,
                leaver_notice="🔒 **User blocked.** Chat ended — you won't be "
                              "matched with them again.",
            )
        else:
            await query.answer("🔒 Blocked — you won't be matched again.")

    elif data.startswith("rpt_"):
        target = db.get_user(int(data[len("rpt_"):]))
        if not target:
            await query.answer("That account no longer exists.", show_alert=True)
            return
        banned_now = db.add_report(user_id, target.user_id)
        in_chat = user.state == ChatState.CHATTING and user.partner_id == target.user_id
        if in_chat:
            await close_chat(
                context,
                user_id,
                leaver_notice="🚩 **Report submitted.** This user won't be "
                              "matched with you again.",
            )
        else:
            await query.answer("🚩 Report submitted — thank you!")
            await safe_edit(
                query,
                "🚩 **Report submitted.**\n\nThis user won't be matched with "
                "you again.",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(),
            )
        if banned_now:
            db.remove_from_queue(target.user_id)
            try:
                await context.bot.send_message(
                    chat_id=target.user_id,
                    text="🚫 Your account has been restricted because of "
                         "multiple reports from other users.",
                    reply_markup=main_menu_keyboard(),
                )
            except Exception as e:
                logger.warning(f"Failed to notify banned user {target.user_id}: {e}")

    elif data.startswith("addc_"):
        target = db.get_user(int(data[len("addc_"):]))
        if not target:
            await query.answer("That account no longer exists.", show_alert=True)
            return
        if db.add_contact(user_id, target.user_id):
            await query.answer("➕ Added to your contacts!")
        else:
            await query.answer("Already in your contacts.")

    elif data.startswith("notify_"):
        target = db.get_user(int(data[len("notify_"):]))
        if not target:
            await query.answer("That account no longer exists.", show_alert=True)
            return
        enabled = not user.notify_on_end
        db.set_notify_end(user_id, enabled)
        await query.answer(
            "🔔 You'll get a ping when the chat ends."
            if enabled
            else "🔕 Chat-end alerts are off."
        )
        await safe_edit(
            query,
            build_user_card(target, user_id),
            parse_mode="Markdown",
            reply_markup=profile_view_keyboard(
                target.user_id, user_id in target.liked_by, notify=enabled
            ),
        )

    elif data.startswith("like_toggle_"):
        target = db.get_user(int(data[len("like_toggle_"):]))
        if not target:
            await query.answer("That account no longer exists.", show_alert=True)
            return
        if user_id in target.liked_by:
            db.unlike(user_id, target.user_id)
            await query.answer("💔 Like removed")
        else:
            is_new, total = db.add_like(user_id, target.user_id)
            if is_new:
                await query.answer("❤️ Liked!")
                try:
                    await context.bot.send_message(
                        chat_id=target.user_id,
                        text=(
                            f"❤️ Someone liked your profile! Total likes: {total}"
                        ),
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to notify like to {target.user_id}: {e}"
                    )
            else:
                await query.answer("You can't like this profile.")
        liked = user_id in target.liked_by
        await safe_edit(
            query,
            build_user_card(target, user_id),
            parse_mode="Markdown",
            reply_markup=profile_view_keyboard(
                target.user_id, liked, notify=user.notify_on_end
            ),
        )

    # ── Browse People ──────────────────────────────────────
    elif data in ("browse_more", "browse_list"):
        if data == "browse_more":
            offset = context.user_data.get("browse_offset", 0)
            page, total = db.browse_users(user_id, offset, BROWSE_PAGE_SIZE)
            seen = context.user_data.get("browse_ids", [])
            context.user_data["browse_ids"] = (seen + [u.user_id for u in page])[:20]
            context.user_data["browse_offset"] = min(
                20, offset + len(page)
            )
            context.user_data["browse_total"] = total
        text, markup = _browse_state(context, user_id)
        context.user_data["list_ids"] = context.user_data.get("browse_ids", [])
        context.user_data["list_title"] = "🎉 People online"
        context.user_data["list_kind"] = "browse"
        _remember_list_message(context, query)
        await safe_edit(query, text, parse_mode="Markdown", reply_markup=markup)

    elif data == "browse_swipe":
        ids = context.user_data.get("browse_ids") or context.user_data.get(
            "list_ids", []
        )
        if not ids:
            await query.answer("No profiles to swipe yet.", show_alert=True)
            return
        context.user_data["swipe_ids"] = ids[:20]
        _remember_list_message(context, query)
        await _render_swipe(query, context, user_id, 0)

    elif data.startswith("swipe_"):
        try:
            index = int(data[len("swipe_"):])
        except ValueError:
            return
        ids = context.user_data.get("swipe_ids", [])
        if not ids or index < 0 or index >= len(ids):
            await query.answer("No more profiles.", show_alert=True)
            return
        await _render_swipe(query, context, user_id, index)

    elif data == "browse_msg":
        if not context.user_data.get("browse_ids"):
            await query.answer("Open Browse People first.", show_alert=True)
            return
        context.user_data["awaiting_broadcast"] = True
        await safe_edit(
            query,
            "📋 **Send Message to List**\n\n"
            "Type the message you want to send to the people in your current "
            "list.",
            parse_mode="Markdown",
        )

    elif data.startswith("req_view_"):
        requester_id = int(data[len("req_view_"):])
        if db.request_status(requester_id, user_id) != "pending":
            await safe_edit(
                query,
                "⌛ This chat request has expired.",
                reply_markup=main_menu_keyboard(),
            )
            return
        requester = db.get_user(requester_id)
        if not requester:
            await safe_edit(
                query,
                "⌛ This chat request is no longer valid.",
                reply_markup=main_menu_keyboard(),
            )
            return
        await safe_edit(
            query,
            f"🔔 **You have a chat request**\n\n"
            f"- You have up to {CHAT_REQUEST_TTL // 60} minutes after sending "
            f"this message to confirm the chat request.\n\n"
            f"To view the chat request and accept or reject it, click the "
            f"button below 👇\n\n"
            f"{gender_emoji(requester.gender)} **{display_name(requester)}** "
            f"• `{requester.public_id}`",
            parse_mode="Markdown",
            reply_markup=request_keyboard(requester_id),
        )

    elif data.startswith("req_chat_"):
        target = db.get_user(int(data[len("req_chat_"):]))
        if not target:
            await query.answer("That account no longer exists.", show_alert=True)
            return

        ok, reason = db.create_request(user_id, target.user_id)
        if not ok:
            if "Not enough Coins" in reason:
                await query.answer(reason, show_alert=True)
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🪙 {reason}",
                    reply_markup=credit_keyboard(),
                )
            else:
                await query.answer(reason, show_alert=True)
            return

        sender = user
        try:
            await context.bot.send_message(
                chat_id=target.user_id,
                text=(
                    f"🔔 You have a chat request\n"
                    f"- You have up to {CHAT_REQUEST_TTL // 60} minutes after "
                    f"sending this message to confirm the chat request.\n\n"
                    f"To view the chat request and accept or reject it, click "
                    f"the button below 👇"
                ),
                parse_mode="Markdown",
                reply_markup=view_request_keyboard(sender.user_id),
            )
        except Exception as e:
            logger.warning(f"Failed to deliver request to {target.user_id}: {e}")
            db.cancel_request(user_id, target.user_id)
            db.add_coins(user_id, CHAT_REQUEST_COST)  # refund undeliverable request
            await query.answer("Couldn't reach that user.", show_alert=True)
            return

        await query.answer("📨 Request sent!")
        await safe_edit(
            query,
            build_user_card(target, user_id)
            + "\n\n📨 **Request sent — waiting for their answer.**",
            parse_mode="Markdown",
            reply_markup=profile_view_keyboard(
                target.user_id, False, notify=user.notify_on_end
            ),
        )

    elif data.startswith("req_yes_"):
        requester_id = int(data[len("req_yes_"):])
        requester = db.get_user(requester_id)
        me = user

        # Validate everything BEFORE consuming the request, otherwise a
        # failed accept would burn the requester's coins for nothing.
        if db.request_status(requester_id, user_id) != "pending":
            await query.answer("This request is no longer valid.", show_alert=True)
            return
        if not requester:
            db.cancel_request(requester_id, user_id)
            await query.answer("That user no longer exists.", show_alert=True)
            return
        if me.banned or requester.banned:
            await query.answer(
                "🚫 Restricted accounts can't start a chat.", show_alert=True
            )
            return
        if me.state == ChatState.CHATTING or requester.state == ChatState.CHATTING:
            await query.answer(
                "Someone is already in a chat — try again later.", show_alert=True
            )
            return
        if not db.resolve_request(requester_id, user_id, accepted=True):
            await query.answer("This request is no longer valid.", show_alert=True)
            return

        if me.state == ChatState.SEARCHING:
            db.remove_from_queue(user_id)
        if requester.state == ChatState.SEARCHING:
            db.remove_from_queue(requester_id)

        db.pair_users(requester_id, user_id)
        await safe_edit(
            query, "✅ **Request accepted! Say hi 👋**",
            parse_mode="Markdown", reply_markup=chat_keyboard(),
        )
        await notify_partner_found(context, requester_id, user_id)

    elif data.startswith("req_no_"):
        requester_id = int(data[len("req_no_"):])
        if not db.resolve_request(requester_id, user_id, accepted=False):
            await query.answer("This request is no longer valid.", show_alert=True)
            return
        await safe_edit(query, "❌ Request declined.", reply_markup=main_menu_keyboard())
        try:
            await context.bot.send_message(
                chat_id=requester_id,
                text="❌ Your chat request was declined.",
                reply_markup=main_menu_keyboard(),
            )
        except Exception as e:
            logger.warning(f"Failed to notify requester {requester_id}: {e}")

    elif data == "add_contact":
        if user.state != ChatState.CHATTING or not user.partner_id:
            await query.answer("You're not in a chat right now.", show_alert=True)
            return
        if db.add_contact(user_id, user.partner_id):
            await query.answer("➕ Added to your contacts!")
        else:
            await query.answer("Already in your contacts.")

    # ── Chat controls ───────────────────────────────────────
    elif data == "end_chat":
        partner_id = db.end_chat(user_id)
        await safe_edit(
            query, "👋 Chat ended.", reply_markup=main_menu_keyboard()
        )
        if partner_id:
            await context.bot.send_message(
                chat_id=partner_id,
                text="⚠️ Your partner has left the chat.",
                reply_markup=main_menu_keyboard(),
            )
        await _ping_chat_end(context, user_id, partner_id)

    elif data == "report_partner":
        text, _ = await process_report(context, user_id)
        await safe_edit(
            query, text, parse_mode="Markdown", reply_markup=main_menu_keyboard()
        )

    elif data == "next_partner":
        # End current chat and let the user choose who to search for next
        partner_id = db.end_chat(user_id)
        if partner_id:
            await context.bot.send_message(
                chat_id=partner_id,
                text="⚠️ Your partner has left the chat.",
                reply_markup=main_menu_keyboard(),
            )

        await safe_edit(
            query,
            SEARCH_CHOICE_TEXT.format(cost=GIRL_SEARCH_COST),
            parse_mode="Markdown",
            reply_markup=search_choice_keyboard(),
        )

    elif data == "cancel_search":
        db.remove_from_queue(user_id)
        await safe_edit(
            query, "❌ Search cancelled.", reply_markup=main_menu_keyboard()
        )


# ═══════════════════════════════════════════════════════════════════
#  MESSAGE RELAY (forwards messages between paired users)
# ═══════════════════════════════════════════════════════════════════

async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forward any message to the chat partner."""
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user:
        await update.message.reply_text("Please /start first.")
        return

    if user.banned:
        await update.message.reply_text("🚫 Your account is restricted.")
        return

    # Handle profile photo upload (before chat / country logic)
    if context.user_data.get("awaiting_photo"):
        context.user_data["awaiting_photo"] = False
        if update.message.photo:
            db.set_photo(user_id, update.message.photo[-1].file_id)
            await update.message.reply_text(
                "✅ **Profile photo saved!**\n\n"
                "It will be sent to your partner when you get matched.",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(),
            )
        else:
            await update.message.reply_text(
                "❌ That wasn't a photo — photo setting cancelled.",
                reply_markup=settings_keyboard(),
            )
        return

    # Handle location sharing (Nearby search)
    if context.user_data.get("awaiting_location"):
        context.user_data["awaiting_location"] = False
        location = update.message.location
        if location:
            db.set_location(user_id, location.latitude, location.longitude)
            pairs = _nearby_pairs(user_id)
            context.user_data["list_ids"] = [u.user_id for _, u in pairs]
            context.user_data["list_title"] = "📍 People near you"
            context.user_data["list_kind"] = "nearby"
            await update.message.reply_text(
                "✅ Location saved!\n\n" + _list_text("📍 People near you", pairs),
                parse_mode="Markdown",
                reply_markup=user_list_keyboard(pairs),
            )
        else:
            await update.message.reply_text(
                "❌ That wasn't a location — tap 📎 → 📍 Location and send it.",
                reply_markup=share_location_keyboard(),
            )
        return

    # Handle "Find by ID" text input
    if context.user_data.get("awaiting_id"):
        context.user_data["awaiting_id"] = False
        raw = (update.message.text or "").strip()
        target = db.resolve_id(raw) if raw.isdigit() else None
        if not target:
            await update.message.reply_text(
                f"🔎 No account found for ID `{raw or '?'}`.",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(),
            )
            return
        context.user_data["list_ids"] = [target.user_id]
        context.user_data["list_title"] = "🔎 Search result"
        context.user_data["list_kind"] = "plain"
        await reply_profile_card(update.message, user_id, target)
        return

    # Handle verification photo evidence
    if context.user_data.get("awaiting_verify"):
        context.user_data["awaiting_verify"] = False
        gender = context.user_data.pop("verify_gender", None) or user.gender
        if update.message.photo and gender:
            db.queue_verification(user_id, gender, update.message.photo[-1].file_id)
            await update.message.reply_text(
                "🪩 **Verification submitted!**\n\n"
                "An admin will review your photo — you'll get a message when "
                "it's approved.",
                parse_mode="Markdown",
                reply_markup=settings_keyboard(),
            )
        else:
            await update.message.reply_text(
                "❌ Verification cancelled — pick your gender first, then send "
                "a photo.",
                reply_markup=settings_keyboard(),
            )
        return

    # Handle country text input
    if context.user_data.get("awaiting_country"):
        country = update.message.text.strip()
        db.update_country(user_id, country)
        context.user_data["awaiting_country"] = False
        await update.message.reply_text(
            f"✅ Country set to **{country}**\n\n"
            "Who would you like to chat with?",
            parse_mode="Markdown",
            reply_markup=preference_keyboard(),
        )
        return

    # Handle age text input (onboarding + Settings)
    if context.user_data.get("awaiting_age"):
        raw = (update.message.text or "").strip()
        if not (raw.isdigit() and 10 <= int(raw) <= 99):
            await update.message.reply_text(
                "⚠️ Please send your age as a number between 10 and 99.",
                reply_markup=main_reply_keyboard(),
            )
            return
        db.update_age(user_id, int(raw))
        context.user_data["awaiting_age"] = False
        if context.user_data.get("setup_flow"):
            context.user_data["awaiting_city"] = True
            await update.message.reply_text(
                f"✅ Age set to **{raw}**\n\n" + CITY_ASK_TEXT.strip(),
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                f"✅ Age set to **{raw}**",
                parse_mode="Markdown",
                reply_markup=settings_keyboard(),
            )
        return

    # Handle city text input (onboarding + Settings)
    if context.user_data.get("awaiting_city"):
        city = (update.message.text or "").strip()
        if not city:
            await update.message.reply_text(
                "⚠️ Please send a city name.", reply_markup=main_reply_keyboard()
            )
            return
        db.update_city(user_id, city)
        context.user_data["awaiting_city"] = False
        setup_flow = context.user_data.pop("setup_flow", False)
        if setup_flow:
            await update.message.reply_text(
                f"✅ City set to **{city}**",
                parse_mode="Markdown",
                reply_markup=main_reply_keyboard(),
            )
            await update.message.reply_text(
                ALL_SET_TEXT.strip(),
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(),
            )
        else:
            await update.message.reply_text(
                f"✅ City set to **{city}**",
                parse_mode="Markdown",
                reply_markup=settings_keyboard(),
            )
        return

    # Handle profile name text input
    if context.user_data.get("awaiting_name"):
        name = (update.message.text or "").strip()
        if not name:
            await update.message.reply_text(
                "⚠️ Please send a name.", reply_markup=settings_keyboard()
            )
            return
        db.update_name(user_id, name)
        context.user_data["awaiting_name"] = False
        await update.message.reply_text(
            f"✅ Name set to **{name}**",
            parse_mode="Markdown",
            reply_markup=settings_keyboard(),
        )
        return

    # Handle "📋 Send Message to List"
    if context.user_data.get("awaiting_broadcast"):
        context.user_data["awaiting_broadcast"] = False
        text = (update.message.text or "").strip()
        if not text:
            await update.message.reply_text(
                "❌ Empty message cancelled.", reply_markup=main_reply_keyboard()
            )
            return
        recipients = [
            uid
            for uid in context.user_data.get("browse_ids", [])[:20]
            if uid != user_id and db.get_user(uid) and not db.get_user(uid).banned
        ]
        sent = 0
        for uid in recipients:
            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text=f"📩 Message from {display_name(user)}:\n\n{text}",
                )
                sent += 1
            except Exception as e:
                logger.warning(f"Failed to deliver list message to {uid}: {e}")
        await update.message.reply_text(
            f"✅ Message sent to {sent} {'person' if sent == 1 else 'people'}.",
            reply_markup=main_reply_keyboard(),
        )
        return

    # ── Persistent bottom bar buttons ───────────────────────
    if user.state != ChatState.CHATTING and update.message.text:
        text = update.message.text.strip()
        if text == NEW_CHAT_LABEL:
            reply, markup, mode = await begin_search(context, user_id, Gender.ANY)
            await update.message.reply_text(reply, parse_mode=mode, reply_markup=markup)
            return
        if text == BROWSE_LABEL:
            page, total = db.browse_users(user_id, 0, BROWSE_PAGE_SIZE)
            context.user_data["browse_ids"] = [u.user_id for u in page]
            context.user_data["browse_offset"] = len(page)
            context.user_data["browse_total"] = total
            context.user_data["list_ids"] = context.user_data["browse_ids"]
            context.user_data["list_title"] = "🎉 People online"
            context.user_data["list_kind"] = "browse"
            await update.message.reply_text(
                _browse_text(page, total),
                parse_mode="Markdown",
                reply_markup=browse_keyboard(
                    len(page) < total, [(_plain_label(u), u) for u in page]
                ),
            )
            return
        if text == NEARBY_LABEL:
            if not db.has_location(user_id):
                context.user_data["awaiting_location"] = True
                await update.message.reply_text(
                    f"📍 **Nearby People**\n\nShare your location to see people "
                    f"within {NEARBY_RADIUS_KM} km of you.",
                    parse_mode="Markdown",
                    reply_markup=share_location_keyboard(),
                )
            else:
                pairs = _nearby_pairs(user_id)
                context.user_data["list_ids"] = [u.user_id for _, u in pairs]
                context.user_data["list_title"] = "📍 People near you"
                context.user_data["list_kind"] = "nearby"
                await update.message.reply_text(
                    _list_text("📍 People near you", pairs),
                    parse_mode="Markdown",
                    reply_markup=user_list_keyboard(pairs),
                )
            return

    # Check if user is in a chat
    if user.state != ChatState.CHATTING or not user.partner_id:
        # If searching, tell them to wait
        if user.state == ChatState.SEARCHING:
            await update.message.reply_text(
                "⏳ Still searching... please wait.",
                reply_markup=searching_keyboard(),
            )
            return

        await update.message.reply_text(
            "You're not in a chat right now. Use /find to search for a partner.",
            reply_markup=main_menu_keyboard(),
        )
        return

    partner_id = user.partner_id
    msg = update.message

    try:
        # Relay different message types
        if msg.text:
            await context.bot.send_message(chat_id=partner_id, text=f"💬 {msg.text}")
        elif msg.photo:
            await context.bot.send_photo(
                chat_id=partner_id,
                photo=msg.photo[-1].file_id,
                caption=f"📷 {msg.caption or ''}",
            )
        elif msg.sticker:
            await context.bot.send_sticker(chat_id=partner_id, sticker=msg.sticker.file_id)
        elif msg.voice:
            await context.bot.send_voice(chat_id=partner_id, voice=msg.voice.file_id)
        elif msg.video:
            await context.bot.send_video(
                chat_id=partner_id,
                video=msg.video.file_id,
                caption=f"🎥 {msg.caption or ''}",
            )
        elif msg.video_note:
            await context.bot.send_video_note(chat_id=partner_id, video_note=msg.video_note.file_id)
        elif msg.animation:
            await context.bot.send_animation(
                chat_id=partner_id,
                animation=msg.animation.file_id,
                caption=msg.caption or "",
            )
        elif msg.document:
            await context.bot.send_document(
                chat_id=partner_id,
                document=msg.document.file_id,
                caption=f"📎 {msg.caption or ''}",
            )
        elif msg.location:
            await context.bot.send_location(
                chat_id=partner_id,
                latitude=msg.location.latitude,
                longitude=msg.location.longitude,
            )
        else:
            await update.message.reply_text("⚠️ This message type is not supported.")
    except Exception as e:
        logger.error(f"Failed to relay message: {e}")
        await update.message.reply_text("⚠️ Failed to send message to your partner.")


# ═══════════════════════════════════════════════════════════════════
#  PAYMENTS (Telegram Stars coin packs)
# ═══════════════════════════════════════════════════════════════════

async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Validate the order before the user completes a Stars payment."""
    query = update.pre_checkout_query
    parts = (query.invoice_payload or "").split(":")

    ok = len(parts) == 3 and parts[0] == "coin_pack"
    if ok:
        try:
            buyer_id, coins = int(parts[1]), int(parts[2])
            ok = coins > 0 and db.get_user(buyer_id) is not None
        except ValueError:
            ok = False

    if ok:
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Invalid coin package. Please try again.")


async def payment_success_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Award coins after a successful Telegram Stars payment."""
    payment = update.message.successful_payment
    charge_id = payment.telegram_payment_charge_id

    if charge_id in db.processed_charges:
        return
    db.processed_charges.add(charge_id)

    parts = (payment.invoice_payload or "").split(":")
    if len(parts) == 3 and parts[0] == "coin_pack":
        try:
            buyer_id, coins = int(parts[1]), int(parts[2])
        except ValueError:
            buyer_id, coins = None, None
        user = db.get_user(buyer_id) if buyer_id else None
        if user and coins:
            balance = db.add_coins(buyer_id, coins)
            vip_line = ""
            if coins == VIP_PLAN[0]:
                db.set_vip(buyer_id, True)
                vip_line = "\n👑 You're a **VIP** now — Girl searches are free!"
            await update.message.reply_text(
                f"✅ **Payment successful!**\n\n"
                f"🪙 +{coins} Coins\n"
                f"💰 Balance: **{balance} Coins**"
                f"{vip_line}",
                parse_mode="Markdown",
                reply_markup=credit_keyboard(),
            )
            return

    await update.message.reply_text(
        "⚠️ Payment received, but the order could not be verified. "
        "Please contact support with your payment proof."
    )


# ═══════════════════════════════════════════════════════════════════
#  MAIN
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass  # suppress access log spam

def start_health_server():
    port = int(os.getenv("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    logger.info(f"Health check server listening on port {port}")
    server.serve_forever()

async def set_bot_commands(application):
    """Publish the ☰ Menu command list."""
    try:
        await application.bot.set_my_commands(BOT_COMMANDS)
    except Exception as e:
        logger.warning(f"Failed to set bot commands: {e}")


def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN not found! Create a .env file with your bot token.")
        print("   Get one from @BotFather on Telegram.")
        return

    # Set up asyncio event loop for Python 3.12+ / 3.14
    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Start health check server in background thread for Koyeb / cloud platforms
    threading.Thread(target=start_health_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(set_bot_commands).build()

    # Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("find", find_command))
    app.add_handler(CommandHandler("search", find_command))
    app.add_handler(CommandHandler("newchat", newchat_command))
    app.add_handler(CommandHandler("browse", browse_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("credit", credit_command))
    app.add_handler(CommandHandler("vip", vip_command))
    app.add_handler(CommandHandler("link", link_command))
    app.add_handler(CommandHandler("link_anon", link_anon_command))
    app.add_handler(CommandHandler("report", report_command))

    # Admin verification review
    app.add_handler(CommandHandler("verifylist", verifylist_command))
    app.add_handler(CommandHandler("verifyok", verifyok_command))
    app.add_handler(CommandHandler("verifyno", verifyno_command))

    # Payments (Telegram Stars)
    app.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, payment_success_handler))

    # Inline button callbacks
    app.add_handler(CallbackQueryHandler(button_handler))

    # Message relay (all message types)
    app.add_handler(MessageHandler(
        (filters.TEXT & ~filters.COMMAND)
        | filters.PHOTO
        | filters.Sticker.ALL
        | filters.VOICE
        | filters.VIDEO
        | filters.VIDEO_NOTE
        | filters.ANIMATION
        | filters.Document.ALL
        | filters.LOCATION,
        relay_message,
    ))

    print("🤖 Bot is running! Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
