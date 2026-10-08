"""
Telegram Random Chat Bot — Main Bot Logic

Commands:
  /start    — Register & show main menu (supports referral codes)
  /find     — Choose who to search for (Random / Guy / Girl)
  /stop     — End current chat
  /profile  — View your profile
  /credit   — Coin balance, referral link & coin shop
  /link     — Your personal invite link
  /report   — Report your current chat partner
  /help     — Show help

Coins: chatting with anyone is free, searching for a Girl costs coins.
Supports: text, photos, stickers, voice, video, documents, GIFs
"""

import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

from telegram import Update, LabeledPrice
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
    NEARBY_RADIUS_KM,
)
from keyboards import (
    gender_keyboard,
    preference_keyboard,
    country_keyboard,
    main_menu_keyboard,
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
    verify_keyboard,
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


# ═══════════════════════════════════════════════════════════════════
#  MESSAGES / TEMPLATES
# ═══════════════════════════════════════════════════════════════════

WELCOME_MSG = """
🌍 **Welcome to Random Chat Bot!**

Connect with strangers from around the world anonymously.

🔹 Set your **gender** and **country**
🔹 Choose who you want to talk to
🔹 Get matched with a random partner
🔹 Chat freely — your identity stays hidden!

Let's get you set up. First, select your **gender**:
"""

HELP_MSG = """
📖 **How to use this bot:**

/start — Register or reset your profile
/find — Choose who to search for
/stop — End the current conversation
/profile — View your profile
/credit — Coin balance, shop & how to earn Coins
/link — Get your personal invite link
/report — Report your current chat partner
/help — Show this help message

**During a chat:**
• Send any message — it's forwarded anonymously
• Supports: text, photos, stickers, voice, video, GIFs
• Press ⏭️ **Next** to find a new partner
• Press 🛑 **End** to stop chatting
• Press ❤️ **Like** to like your partner's profile
• Press 🚩 **Report** to report your partner

**Settings:**
• Change your gender, country and partner preference
• 📷 Set a profile photo — it's sent to your partner on match
• 🪩 Get Verified — send a photo, an admin reviews it

**Discover people:**
• 📍 Nearby — share your location and see people around you
• 🔎 Find by ID — search anyone with their 6-digit ID (see yours in /profile)
• 📨 Send a chat request ({request_cost} 🪙) — they accept or decline
• ❤️ Like / 💔 Unlike profiles from the profile view
• ➕ Add to Contacts while chatting — see them in 📇 My Contacts

**Coins:**
• Chatting with anyone is **free**
• Searching for a 👩 **Girl** costs **{cost} 🪙 per search**
• Earn Coins by inviting friends with /link
• Buy Coins with Telegram Stars via /credit
"""

PROFILE_TEMPLATE = """
👤 **Your Profile**

🆔 **ID:** `{public_id}`
🔹 **Gender:** {gender}
🔹 **Country:** {country}
🔹 **Looking for:** {preference}
🔹 **Total chats:** {total_chats}
🔹 **Likes:** ❤️ {likes}
🔹 **Coins:** 🪙 {coins}
🔹 **Referrals:** {referrals}
🔹 **Contacts:** 📇 {contacts}
🔹 **Verified:** {verified}
🔹 **Status:** {status}
"""

SEARCH_CHOICE_TEXT = """
👫 **Choose who you want to chat with** 👇

🎲 **Random (Free)**
🕺 **Chat With Guy (Free)**
💃 **Chat With Girl ({cost} 🪙 per search)**

💡 Talking to everyone is free — only searching for Girls costs Coins.
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


# ═══════════════════════════════════════════════════════════════════
#  HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

def format_gender(g):
    if g == Gender.MALE:
        return "👨 Male"
    elif g == Gender.FEMALE:
        return "👩 Female"
    return "Not set"


def format_state(s):
    return {
        ChatState.IDLE: "🟢 Online",
        ChatState.SEARCHING: "🔍 Searching...",
        ChatState.CHATTING: "💬 In Chat",
    }.get(s, "Unknown")


async def notify_partner_found(context, user_id, partner_id):
    """Send 'partner found' notifications to both users."""
    user = db.get_user(user_id)
    partner = db.get_user(partner_id)

    for u, p in [(user, partner), (partner, user)]:
        partner_info = (
            f"🎉 **Partner found!**\n\n"
            f"🌍 Country: **{p.country or 'Unknown'}**\n"
            f"👤 Gender: **{format_gender(p.gender)}**\n"
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
    """Edit a message, ignoring 'message is not modified' errors."""
    try:
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
        public_id=user.public_id,
        gender=format_gender(user.gender),
        country=user.country or "Not set",
        preference=format_gender(user.preferred_gender)
        if user.preferred_gender != Gender.ANY
        else "🌍 Anyone",
        total_chats=user.total_chats,
        likes=user.likes,
        coins=user.coins,
        referrals=user.referral_count,
        contacts=len(user.contacts),
        verified=verified_label(user),
        status=format_state(user.state),
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
    """Profile card for someone else's account (ID search / Nearby / Contacts)."""
    lines = [
        "👤 **Profile**",
        "",
        f"🆔 **ID:** `{target.public_id}`",
        f"🔹 **Gender:** {format_gender(target.gender)}",
        f"🔹 **Verified:** {verified_label(target)}",
        f"🔹 **Country:** {target.country or 'Not set'}",
        f"🔹 **Likes:** ❤️ {target.likes}",
        f"🔹 **Total chats:** {target.total_chats}",
        f"🔹 **Status:** {format_state(target.state)}",
    ]
    distance = db.distance_km(viewer_id, target.user_id)
    if distance is not None:
        lines.insert(
            4, f"📍 **Distance:** {distance:.0f} km away"
        )
    lines += [
        "",
        f"📨 Chat request costs **{CHAT_REQUEST_COST} 🪙**",
    ]
    return "\n".join(lines)


def _plain_label(user) -> str:
    name = f"@{user.username}" if user.username else f"ID {user.public_id}"
    return f"{name} • {format_gender(user.gender)}"


def _nearby_pairs(viewer_id: int) -> list:
    pairs = []
    for target, dist in db.nearby_users(viewer_id):
        name = f"@{target.username}" if target.username else f"ID {target.public_id}"
        pairs.append((
            f"📍 {dist:.0f} km • {name} • {format_gender(target.gender)}",
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
            name = f"@{user.username}" if user.username else f"ID {user.public_id}"
            prefix = f"📍 {dist:.0f} km • " if dist is not None else "📍 "
            pairs.append((f"{prefix}{name}", user))
        else:
            pairs.append((_plain_label(user), user))
    return pairs


def _list_text(title: str, pairs) -> str:
    if not pairs:
        return f"{title}\n\nNo one here right now."
    return f"{title}\n\n👥 {len(pairs)} found — tap one to open their profile:"


async def begin_search(context, user_id: int, search_pref: Gender):
    """
    Start a search with the given per-search filter.
    Charges coins when searching for a Girl.
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
    if search_pref == Gender.FEMALE:
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
    db.end_chat(reporter_id)

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
    else:
        try:
            await context.bot.send_message(
                chat_id=partner_id,
                text="⚠️ Your partner has left the chat.",
                reply_markup=main_menu_keyboard(),
            )
        except Exception as e:
            logger.warning(f"Failed to notify partner {partner_id}: {e}")

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
    ref_code = context.args[0] if context.args else None
    is_new = db.get_user(user_id) is None

    # End any existing chat
    partner_id = db.end_chat(user_id)
    if partner_id:
        await context.bot.send_message(
            chat_id=partner_id,
            text="⚠️ Your partner has left the chat.",
            reply_markup=main_menu_keyboard(),
        )

    db.remove_from_queue(user_id)
    db.register_user(user_id, username)

    welcome = WELCOME_MSG

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
        partner_id = db.end_chat(user_id)
        await update.message.reply_text(
            "👋 You left the chat.",
            reply_markup=main_menu_keyboard(),
        )
        if partner_id:
            await context.bot.send_message(
                chat_id=partner_id,
                text="⚠️ Your partner has left the chat.",
                reply_markup=main_menu_keyboard(),
            )
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
        await safe_edit(
            query,
            f"✅ You'll be matched with: **{label}**\n\n"
            "🎉 You're all set! Use the menu below to find a partner.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
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
        liked = user_id in target.liked_by
        await safe_edit(
            query,
            build_user_card(target, user_id),
            parse_mode="Markdown",
            reply_markup=profile_view_keyboard(target.user_id, liked),
        )

    elif data.startswith("like_toggle_"):
        target = db.get_user(int(data[len("like_toggle_"):]))
        if not target:
            await query.answer("That account no longer exists.", show_alert=True)
            return
        if user_id in target.liked_by:
            _, total = db.unlike(user_id, target.user_id)
            await query.answer("💔 Like removed")
        else:
            _, total = db.add_like(user_id, target.user_id)
            await query.answer("❤️ Liked!")
            try:
                await context.bot.send_message(
                    chat_id=target.user_id,
                    text=f"❤️ Someone liked your profile! Total likes: {total}",
                )
            except Exception as e:
                logger.warning(f"Failed to notify like to {target.user_id}: {e}")
        liked = user_id in target.liked_by
        await safe_edit(
            query,
            build_user_card(target, user_id),
            parse_mode="Markdown",
            reply_markup=profile_view_keyboard(target.user_id, liked),
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
                    f"📨 **Chat request**\n\n"
                    f"*{sender.username or 'Someone'}* (ID `{sender.public_id}`) "
                    f"wants to chat with you.\n"
                    f"Accept to start chatting right away."
                ),
                parse_mode="Markdown",
                reply_markup=request_keyboard(sender.user_id),
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
            reply_markup=profile_view_keyboard(target.user_id, False),
        )

    elif data.startswith("req_yes_"):
        requester_id = int(data[len("req_yes_"):])
        if not db.resolve_request(requester_id, user_id, accepted=True):
            await query.answer("This request is no longer valid.", show_alert=True)
            return

        requester = db.get_user(requester_id)
        me = user
        if not requester:
            await query.answer("That user no longer exists.", show_alert=True)
            return
        if me.state == ChatState.CHATTING or requester.state == ChatState.CHATTING:
            await query.answer("Someone is already in a chat.", show_alert=True)
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
        await update.message.reply_text(
            build_user_card(target, user_id),
            parse_mode="Markdown",
            reply_markup=profile_view_keyboard(
                target.user_id, user_id in target.liked_by
            ),
        )
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
            await update.message.reply_text(
                f"✅ **Payment successful!**\n\n"
                f"🪙 +{coins} Coins\n"
                f"💰 Balance: **{balance} Coins**",
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

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("find", find_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("credit", credit_command))
    app.add_handler(CommandHandler("link", link_command))
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
