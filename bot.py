"""
Telegram Random Chat Bot — Main Bot Logic

Commands:
  /start      — Register & show main menu (supports referral codes)
  /newchat    — Start a random anonymous chat
  /search     — Start a search (Random)
  /stop       — End current chat
  /profile    — View your profile
  /credit     — Coin balance, referral link & coin shop
  /vip        — Upgrade to VIP
  /link       — Your personal invite link
  /link_anon  — Your anonymous chat link
  /report     — Report your current chat partner
  /help       — Show help

Coins: chatting with anyone is free, searching for a Guy or a Girl is
turned off for now (only the free Random search is offered), a chat
request costs 2 coins. Every new user starts with 2 coins.
Supports: text, photos, stickers, voice, video, documents, GIFs
"""

import os
import sys
import re
import io
import asyncio
import base64
import logging
import sqlite3
import time
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

import qrcode

from telegram import (
    Update,
    LabeledPrice,
    BotCommand,
    Bot,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
)
from telegram.error import BadRequest, Forbidden
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
    Availability,
    STARTING_COINS,
    REFERRAL_REWARD,
    REFERRED_BONUS,
    GIRL_SEARCH_COST,
    GUY_SEARCH_COST,
    CHAT_REQUEST_COST,
    DIRECT_MESSAGE_COST,
    LIST_MESSAGE_COST,
    NOTIFY_COST,
    CHAT_REQUEST_TTL,
    NEARBY_RADIUS_KM,
    NEARBY_WIDE_RADIUS_KM,
    EARTH_RADIUS_KM,
    BROWSE_PAGE_SIZE,
    DAILY_REWARD_COINS,
    DAILY_CHECKIN_COINS,
    REMINDER_HOUR_START,
    REMINDER_HOUR_END,
    WEEKLY_REWARD_COINS,
    POINT_CAPS,
    AVAILABILITY_TTL,
    format_public_id,
    public_id_slug,
    bot_today,
    bot_now,
    current_week_id,
    previous_week_id,
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
    nearby_list_keyboard,
    share_location_keyboard,
    profile_view_keyboard,
    request_keyboard,
    view_request_keyboard,
    viewed_by_keyboard,
    browse_keyboard,
    browse_menu_keyboard,
    blocked_users_keyboard,
    promo_keyboard,
    swipe_keyboard,
    vip_keyboard,
    upi_plan_keyboard,
    upi_paid_keyboard,
    UPI_VIP_PLANS,
    verify_keyboard,
    force_join_keyboard,
    discover_keyboard,
    privacy_keyboard,
    availability_keyboard,
    games_menu_keyboard,
    game_controls_keyboard,
    checkin_keyboard,
    leaderboard_keyboard,
    theme_keyboard,
    NEW_CHAT_LABEL,
    BROWSE_LABEL,
    NEARBY_LABEL,
    SECURE_LABELS,
    CONTACT_PROFILE_LABEL,
    END_CHAT_LABEL,
    DELETE_LABEL,
)
import games as games_mod
from themes import THEMES, BUYABLE_THEMES, get_theme, theme_line
from animations import (
    ANIMATIONS_ENABLED,
    animate_edit,
    animate_search,
    animate_photo_card,
    animate_message_caption,
    animated_reply,
    typing_pulse,
    match_photo_frames,
    bounce_frames,
    coin_frames,
    emoji_cycle_frames,
)

load_dotenv()
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Bump on every deploy so the startup log + /version show exactly what's live.
BOT_VERSION = "2026.10.19.1"

BOT_TOKEN = os.getenv("BOT_TOKEN")
# Telegram user ID of the admin (you) — reviews verification photos.
_admin = os.getenv("ADMIN_ID", "")
ADMIN_ID = int(_admin) if _admin.strip().isdigit() else None

# UPI ID for VIP purchases (QR codes are generated from this).
UPI_ID = "9395029363@naviaxis"

# Forced channel subscription — users must join before using the bot.
# FORCE_CHANNEL: @channelusername, channelusername or -100… channel id.
# FORCE_CHANNEL_INVITE: invite link for private channels (https://t.me/+…).
FORCE_CHANNEL = os.getenv("FORCE_CHANNEL", "").strip()
FORCE_CHANNEL_INVITE = os.getenv("FORCE_CHANNEL_INVITE", "").strip()

# Free database persistence: the bot keeps its SQLite file backed up in a
# private Telegram channel and restores it on startup — so users, coins and
# chats survive redeploys even on free hosts that wipe the disk every time.
# Create a private channel, add the bot as ADMIN (post + pin messages), and
# set BACKUP_CHANNEL=@yourchannel or the -100… channel id.
BACKUP_CHANNEL = os.getenv("BACKUP_CHANNEL", "").strip()
BACKUP_INTERVAL = int(os.getenv("BACKUP_INTERVAL", "600"))  # 10 minutes
# Optional SECOND token — a dedicated "backup account" bot that handles all
# backup traffic (upload/restore/pin/delete in BACKUP_CHANNEL). The main bot
# keeps serving users untouched. Both bots must be ADMIN of the channel.
# Leave empty to back up with the main bot.
BACKUP_BOT_TOKEN = os.getenv("BACKUP_BOT_TOKEN", "").strip()
# How many snapshots stay in the channel. Old ones used to be deleted after
# every upload — one bad upload could therefore destroy the LAST good copy.
# Keep a small history so a wiped disk can always be rolled back.
BACKUP_KEEP = int(os.getenv("BACKUP_KEEP", "5"))
# How many recent channel messages are inspected when looking for backups.
BACKUP_SCAN_LIMIT = 20

# ── Online backup: a PRIVATE GitHub repository ─────────────────────
# Every snapshot is COMMITTED to the repo, so git keeps every previous
# version forever — a bad upload cannot destroy the copy before it, and the
# file lives online where a wiped deploy disk can never reach it.
# 1. Create a PRIVATE repo (e.g. yourname/telegram-db-backup)
# 2. GitHub → Settings → Developer settings → Fine-grained tokens →
#    Contents: Read & Write, scoped to that repo
# 3. Set both variables below (in .env here, and in your host's env vars)
BACKUP_GITHUB_REPO = os.getenv("BACKUP_GITHUB_REPO", "").strip()  # owner/name
BACKUP_GITHUB_TOKEN = os.getenv("BACKUP_GITHUB_TOKEN", "").strip()
BACKUP_GITHUB_PATH = os.getenv("BACKUP_GITHUB_PATH", "bot.db").strip()
# How many committed versions are probed on startup (biggest one wins).
BACKUP_GITHUB_HISTORY = int(os.getenv("BACKUP_GITHUB_HISTORY", "10"))

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
    BotCommand("checkin", "🎁 Daily check-in reward"),
    BotCommand("games", "🎮 Play mini-games"),
    BotCommand("leaderboard", "🏆 Weekly leaderboard"),
    BotCommand("themes", "🎨 Customize your theme"),
    BotCommand("avail", "🟢 Set availability status"),
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
• 🔎 **Find by ID** — search anyone with their 6-digit ID or `/user_xxx` ID (see yours in /profile)
• 📨 **Chat Request** ({request_cost} 🪙) — they accept within two minutes
• 📨 **Direct Message** ({dm_cost} 🪙) — start a chat instantly from a profile card
• ❤️ Like / 💔 Unlike profiles from the profile view
• ➕ Add to Contacts while chatting — see them in 📇 My Contacts
• 🔔 **Notify me when chat ends** — {notify_cost} 🪙 to switch on (👑 VIP free)

**Profile:**
• Set your **name, age, city** and 📷 a profile photo
• No photo yet? An **AI avatar** shows on your profile card automatically
• 🪩 Get Verified — send a photo, an admin reviews it
• ⏰ **Daily Reminder** (⚙️ Settings) — one message a day nudging you to
  come back and talk to someone

**Coins:**
• 🎁 Every new account starts with **{free} 🪙**
• 🎁 **Daily Check-in** — claim **{checkin} 🪙** once per day
• 🏆 **Weekly Leaderboard** — top 3 earn 6 / 4 / 2 coins every week
• Chatting with anyone is **free**
• 🎲 Random search is **free** for everyone — searching for a 🕺 **Guy**
  or a 👩 **Girl** is turned off for now
• Earn Coins by inviting friends with /link
• Buy Coins with Telegram Stars via /credit

**Fun:**
• 🎮 **Mini-Games** — Would You Rather, Truth or Dare, Quiz Battle,
  Emoji Guess, Rapid-Fire, Guess the Number, Friendship Quiz
• 🎨 **Custom Themes** — unlock with coins (/themes)
• 🟢 **Availability** — Ready / Busy / Invisible (/avail)
"""

HELP_KWARGS = dict(
    request_cost=CHAT_REQUEST_COST,
    dm_cost=DIRECT_MESSAGE_COST,
    notify_cost=NOTIFY_COST,
    free=STARTING_COINS,
    checkin=DAILY_CHECKIN_COINS,
)

PROFILE_TEMPLATE = """
{badge} **{name}**
Age: {age} • City: {city}

👁 {online}
ID: {public_id}

{bio_line}{interests_line}{languages_line}
❤️ {likes} likes
🪙 {coins} Coins
🌍 Country: {country}
🔹 Looking for: {preference}
🔹 Total chats: {total_chats}
📇 Contacts: {contacts}
👥 Referrals: {referrals}
🪩 {verified}
🎨 Theme: {theme}
"""

SEARCH_CHOICE_TEXT = """
🎲 **Choose who you want to chat with** 👇
"""

# Sent when a chat ends (MeChat wording) — the choose-menu rides on top.
CHAT_ENDED_TEXT = "User {who} has left the chat."
DELETE_HINT_TEXT = (
    "🗑 You can delete messages you sent within 30 minutes after the chat "
    "ends.\n/delet_messages_{slug}"
)

# Secure Chat notices (verbatim from the reference bot).
SECURE_ON_SELF = (
    "✅ **Private chat activated!**\n\n"
    "- When activated, your sent media will no longer have the ability to be "
    "forwarded, screenshot, or saved by contact!"
)
SECURE_OFF_SELF = (
    "🔓 **Private chat deactivated.**\n\n"
    "- Your media can be forwarded and saved again."
)
SECURE_ON_PARTNER = (
    "🤖 **Chat Notice** 👇\n\n" + SECURE_ON_SELF
)
SECURE_OFF_PARTNER = (
    "🤖 **Chat Notice** 👇\n\n" + SECURE_OFF_SELF
)

NAME_ASK_TEXT = """
✏️ **What should people call you?**

Send your name — this is what others see on your profile card.
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

SEARCHING_TEXT = """
🔍 **Searching for your anonymous contact** 🎀💘
🎲 -Random Search

⏳ Please wait up to 2 minutes.
👥 {count} people searching right now
❌ Tap **Cancel Search** to stop anytime.
"""

PROMO_TEXT = (
    "Want to start an anonymous chat? 😎\n\n"
    "Tap 🎲 **Start Random Chat** and start chatting now.\n"
    f"🎁 Girls receive **{DAILY_REWARD_COINS} free coin** per match! 👇"
)


async def send_promo(context, chat_id: int) -> None:
    """MeChat-style pinned promo: sent once, then kept pinned."""
    ud = _user_data(context, chat_id)
    promo_id = ud.get("promo_msg_id")
    if not promo_id:
        try:
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=PROMO_TEXT,
                parse_mode="Markdown",
                reply_markup=promo_keyboard(None),
            )
        except Exception as e:  # noqa: BLE001
            logger.debug(f"promo skipped for {chat_id}: {e}")
            return
        promo_id = getattr(msg, "message_id", None)
        ud["promo_msg_id"] = promo_id
        if not promo_id:
            return
    try:
        await context.bot.pin_chat_message(chat_id=chat_id, message_id=promo_id)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"pin skipped for {chat_id}: {e}")


# ── ⏰ Daily reminder: one message a day, reminding the user to come
#    back and talk to someone ────────────────────────────────────────

REMINDER_INTERVAL = 3600  # seconds between daily-reminder sweeps

REMINDER_TEXT = (
    "⏰ **Daily reminder**\n\n"
    "Someone out there wants to talk 💬 — come back and find a partner "
    "for a chat!\n\n"
    "Tap a button below to start."
)


def reminder_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Start Random Chat", callback_data="search_random")],
        [InlineKeyboardButton("🎉 Browse People", callback_data="browse_menu")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="back_menu")],
    ])


async def send_due_reminders(bot, current_hour=None, today=None) -> int:
    """
    Nudge every user who switched ⏰ Daily Reminder on — at most ONE
    message per user per day, and only inside the waking-hours window.
    Returns how many reminders went out.
    """
    hour = time.localtime().tm_hour if current_hour is None else current_hour
    if not (REMINDER_HOUR_START <= hour < REMINDER_HOUR_END):
        return 0
    date = today or bot_today()
    sent = 0
    for user in list(db.users.values()):
        if not user.daily_reminder or user.reminder_date == date or user.banned:
            continue
        try:
            await bot.send_message(
                chat_id=user.user_id,
                text=REMINDER_TEXT,
                parse_mode="Markdown",
                reply_markup=reminder_keyboard(),
            )
            db.mark_reminder_sent(user.user_id, date)
            sent += 1
        except Exception as e:  # noqa: BLE001 — one dead chat stops no sweep
            logger.debug(f"Daily reminder to {user.user_id} failed: {e}")
    return sent


async def _reminder_loop(bot) -> None:
    """Hourly sweep — sends at most one reminder per user per day."""
    while True:
        await asyncio.sleep(REMINDER_INTERVAL)
        try:
            sent = await send_due_reminders(bot)
            if sent:
                logger.info(f"⏰ Daily reminders sent to {sent} users.")
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Reminder loop error: {e}")


# ── 📨 Daily broadcast: one automated message a day to EVERY member ──
# Configurable via .env. Leave DAILY_BROADCAST empty to disable it.

DAILY_BROADCAST_TEXT = os.getenv("DAILY_BROADCAST", "").strip()
# Hour (bot timezone, 0-23) the daily message goes out; default 18 (6 PM).
DAILY_BROADCAST_HOUR = int(os.getenv("DAILY_BROADCAST_HOUR", "18"))
# Small delay between sends so we stay well under Telegram's flood limit.
DAILY_BROADCAST_DELAY = float(os.getenv("DAILY_BROADCAST_DELAY", "0.05"))
# How often the sweep loop wakes up to check whether it's time to send.
BROADCAST_SWEEP_INTERVAL = 60  # seconds


def broadcast_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Start Chatting", callback_data="find_partner")],
        [InlineKeyboardButton("🎁 Daily Check-in", callback_data="checkin")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="back_menu")],
    ])


def _broadcast_due(hour: int) -> bool:
    """True once the local clock has reached today's broadcast hour."""
    return hour >= DAILY_BROADCAST_HOUR


async def send_daily_broadcast(bot, current_hour=None, today=None) -> int:
    """
    Send DAILY_BROADCAST_TEXT to EVERY member — at most one message per
    user per day. Users who already got today's broadcast (tracked in
    user.broadcast_date) are skipped, so restarts / overlapping sweeps can
    never double-send. Banned users and dead chats are skipped silently.
    Returns how many messages went out.
    """
    if not DAILY_BROADCAST_TEXT:
        return 0
    hour = bot_now().hour if current_hour is None else current_hour
    if not _broadcast_due(hour):
        return 0
    date = today or bot_today()
    sent = 0
    for user in list(db.users.values()):
        if user.banned or user.broadcast_date == date:
            continue
        try:
            await bot.send_message(
                chat_id=user.user_id,
                text=DAILY_BROADCAST_TEXT,
                parse_mode="Markdown",
                reply_markup=broadcast_keyboard(),
            )
            db.mark_broadcast_sent(user.user_id, date)
            sent += 1
            if DAILY_BROADCAST_DELAY > 0:
                await asyncio.sleep(DAILY_BROADCAST_DELAY)
        except Exception as e:  # noqa: BLE001 — one dead chat stops no sweep
            logger.debug(f"Daily broadcast to {user.user_id} failed: {e}")
    return sent


async def _broadcast_loop(bot) -> None:
    """Wake up every minute; send the daily message once the hour is reached."""
    while True:
        await asyncio.sleep(BROADCAST_SWEEP_INTERVAL)
        try:
            sent = await send_daily_broadcast(bot)
            if sent:
                logger.info(f"📨 Daily broadcast sent to {sent} members.")
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Broadcast loop error: {e}")


WEEKLY_SWEEP_INTERVAL = 1800  # every 30 min: finalize week + expire statuses


async def _weekly_sweep_loop(bot) -> None:
    """Periodic maintenance: weekly leaderboard rewards + stale statuses.

    Rewards are finalized atomically inside the Database (idempotent), so
    overlapping runs can never double-pay the top 3.
    """
    while True:
        await asyncio.sleep(WEEKLY_SWEEP_INTERVAL)
        try:
            expired = await asyncio.to_thread(db.expire_stale_availability)
            if expired:
                logger.info(f"🟢 Expired {expired} stale availability statuses.")
            result = await asyncio.to_thread(db.sweep_weekly_rewards)
            if result:
                await _announce_weekly_winners(bot, result)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Weekly sweep error: {e}")


async def _announce_weekly_winners(bot, result: dict) -> None:
    """Tell the top 3 (and everyone interested) that rewards were paid."""
    week = result.get("week", "?")
    results = result.get("results", [])
    if not results:
        return
    medals = ["🥇 1st", "🥈 2nd", "🥉 3rd"]
    for res in results:
        rank = res.get("rank", 0)
        uid = res.get("user_id")
        coins = res.get("coins", 0)
        points = res.get("points", 0)
        if not uid or not coins:
            continue
        medal = medals[rank - 1] if 1 <= rank <= 3 else f"{rank}."
        user = db.get_user(uid)
        try:
            await bot.send_message(
                chat_id=uid,
                text=(
                    f"🏆 **Weekly leaderboard reward!**\n\n"
                    f"You finished {medal} in {week} with **{points} points**.\n"
                    f"🪙 **+{coins} coins** added — balance: "
                    f"**{user.coins if user else '?'} 🪙**"
                ),
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(),
            )
        except Exception as e:  # noqa: BLE001 — dead chats skip silently
            logger.debug(f"Weekly reward notify to {uid} failed: {e}")


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
        f"💡 *Chatting with anyone is free — a 📨 Chat Request "
        f"{CHAT_REQUEST_COST} 🪙 "
        f"and a 📨 Direct Message from a profile {DIRECT_MESSAGE_COST} 🪙.*\n"
        f"🎁 New accounts start with **{STARTING_COINS} free Coins**."
    )


VIP_PLAN = (6200, 740)  # (coins, stars) — the VIP pack sold via /vip


def vip_expiry_label(user) -> str:
    """Human expiry date for a timed VIP, or '' for permanent / no VIP."""
    if user.vip and user.vip_expires_at:
        return datetime.fromtimestamp(user.vip_expires_at).strftime("%d %b %Y")
    return ""


def vip_text(user) -> str:
    if user.vip:
        until = vip_expiry_label(user)
        status = (
            f"👑 You're a VIP — active until **{until}**!"
            if until else
            "👑 You're a VIP already — thank you!"
        )
    else:
        status = "🔥 **Upgrade to VIP**"
    return (
        f"{status}\n\n"
        f"👑 **VIP benefits**\n"
        f"• 👑 **Partner preference** — choose 👨 Males or 👩 Females to "
        f"chat with (free members always match 🌍 Anyone)\n"
        f"• 🔔 Chat-end alerts are **free** (everyone else pays "
        f"{NOTIFY_COST} 🪙 to switch them on)\n"
        f"• 👑 VIP badge on your profile card and in every match\n"
        f"• 🔥 VIP label next to your name in lists\n\n"
        f"👑 **{VIP_PLAN[0]} Coins** for **⭐{VIP_PLAN[1]}**\n"
        f"💡 Buy it from the button below — paid securely with Telegram Stars.\n"
        f"📱 Or pay with **UPI / PhonePe** from the button below."
    )


_UPI_PRICES = dict(UPI_VIP_PLANS)  # days -> INR


def upi_qr_png(amount: int, days: int) -> io.BytesIO:
    """Generate a UPI deep-link QR code in memory (PNG)."""
    url = (
        f"upi://pay?pa={UPI_ID}&pn=Random%20Chat%20Bot"
        f"&am={amount}&cu=INR&tn=VIP%20{days}%20Days"
    )
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


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


ONLINE_WINDOW = 300  # seconds a user counts as Online after their last activity


def _ago(seconds: float) -> str:
    """'just now' / '40 minutes ago' / '1 hour ago' / '3 days ago'."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'' if minutes == 1 else 's'} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'' if hours == 1 else 's'} ago"
    days = hours // 24
    if days < 30:
        return f"{days} day{'' if days == 1 else 's'} ago"
    months = days // 30
    if months < 12:
        return f"{months} month{'' if months == 1 else 's'} ago"
    years = days // 365
    return f"{max(1, years)} year{'' if years == 1 else 's'} ago"


def last_seen_stamp(user) -> float:
    """Heartbeat time — falls back to registration for pre-heartbeat rows."""
    return getattr(user, "last_seen", 0.0) or user.registered_at or 0.0


def activity_line(user) -> str:
    """⌛ Was online 40 minutes ago (In chat💬) — reference-bot activity row."""
    delta = time.time() - last_seen_stamp(user)
    if delta <= ONLINE_WINDOW:
        line = "👁 Online now"
    else:
        line = f"⌛ Was online {_ago(delta)}"
    if user.state == ChatState.CHATTING:
        line += " (In chat💬)"
    elif user.state == ChatState.SEARCHING:
        line += " (Searching🔍)"
    return line


def format_online(user) -> str:
    """👁 Online status line shown on profile cards.

    Presence comes from the user's own last-seen heartbeat (updated on
    every message/tap) — never from the stored chat state, so a stale
    IDLE row can't claim to be online forever.
    """
    avail = getattr(user, "availability", Availability.READY)
    if avail == Availability.INVISIBLE:
        return "⚫ Invisible"
    last_seen = last_seen_stamp(user)
    if time.time() - last_seen > ONLINE_WINDOW:
        return activity_line(user)
    if user.state == ChatState.CHATTING:
        base = "👁 Online (Chatting🗣)"
    elif user.state == ChatState.SEARCHING:
        base = "👁 Online (Searching🔍)"
    else:
        base = "👁 Online"
    if avail == Availability.BUSY:
        return f"{base} • 🟡 Busy"
    return f"{base} • 🟢 Ready"


def _bar(user, secure: Optional[bool] = None) -> ReplyKeyboardMarkup:
    """Bottom bar for THIS user: chat controls while chatting, the three
    discovery buttons otherwise."""
    if secure is None:
        secure = bool(getattr(user, "secure_chat", False))
    in_chat = user.state == ChatState.CHATTING and bool(user.partner_id)
    return main_reply_keyboard(secure=secure, in_chat=in_chat)


def md_escape(text: str) -> str:
    """Escape user-supplied text for Telegram's legacy Markdown parse mode,
    so a name containing _ * [ ` can't break the whole message."""
    return "".join("\\" + ch if ch in "\\_*[`" else ch for ch in text)


def display_name(user, viewer=None) -> str:
    """Display name for lists/cards.

    @username is a direct link to a personal Telegram account, so it is
    NEVER shown to other users — not even VIP. Only the admin (verification)
    and the account owner themselves can see it.
    """
    if user.name:
        return user.name
    if user.username and viewer is not None and (
        viewer.user_id == user.user_id
        or (ADMIN_ID is not None and viewer.user_id == ADMIN_ID)
    ):
        return f"@{user.username}"
    return "Stranger"


# ── Bot username cache (profile deep links, referral links) ─────

_bot_username = ""


def set_bot_username(name: str) -> None:
    global _bot_username
    _bot_username = (name or "").lstrip("@")


def bot_username() -> str:
    return _bot_username


async def ensure_bot_username(bot) -> str:
    """Fetch the bot's @username once and cache it for every later render."""
    if _bot_username:
        return _bot_username
    if not hasattr(bot, "get_me"):
        return _bot_username
    try:
        me = await bot.get_me()
    except Exception as e:  # noqa: BLE001 — never block a reply on this
        logger.debug(f"Could not cache bot username: {e}")
        return _bot_username
    set_bot_username(me.username)
    return _bot_username


def public_id_link(user, label: str | None = None) -> str:
    """
    A tappable user ID — tapping it opens this user's profile card
    (via the bot's /start chat_<slug> deep link).

    Falls back to the old monospace code span when the bot username is
    not known yet (e.g. in tests): the text stays copyable either way.
    """
    if user is None:
        return "`?`"
    label = label or format_public_id(user)
    name = _bot_username
    if not name:
        return f"`{label}`"
    return f"[{label}](https://t.me/{name}?start=chat_{public_id_slug(user)})"


def _user_data(context, user_id: int) -> dict:
    """Per-user data store — works for the OTHER side of a match too.

    PTB exposes `Application.user_data` as a read-only `MappingProxyType`,
    so we must reach the mutable backing defaultdict `_user_data` to write
    into another user's slot.
    """
    app = getattr(context, "application", None)
    if app is not None:
        store = getattr(app, "_user_data", None)
        if store is not None:
            return store.setdefault(user_id, {})
    return context.user_data


# ── Mandatory profile fields (name → age → city) ────────────────

PROFILE_FIELDS = ("name", "age", "city")

_SETUP_PROMPTS = {"name": NAME_ASK_TEXT, "age": AGE_ASK_TEXT, "city": CITY_ASK_TEXT}


def missing_profile_fields(user) -> list[str]:
    """Mandatory profile fields the user still owes, in asking order."""
    return [f for f in PROFILE_FIELDS if not getattr(user, f, None)]


def profile_setup_reply(context, user):
    """Arm the name→age→city chain for the first missing field.

    Returns (text, reply_markup, parse_mode) for the caller to send/edit,
    or None when the profile is already complete.
    """
    missing = missing_profile_fields(user)
    if not missing:
        return None
    field = missing[0]
    context.user_data["setup_flow"] = True
    context.user_data[f"awaiting_{field}"] = True
    return (
        f"⚠️ Your profile is incomplete — **{field}** is required.\n\n"
        + _SETUP_PROMPTS[field].strip(),
        None,
        "Markdown",
    )


async def _next_setup_step(update, context, user_id: int, done_line: str) -> None:
    """After one onboarding field is saved: ask for the next missing one,
    or close the flow — all-set message, promo and the force-join gate."""
    user = db.get_user(user_id)
    for field in PROFILE_FIELDS:
        if not getattr(user, field, None):
            context.user_data["setup_flow"] = True
            context.user_data[f"awaiting_{field}"] = True
            await update.message.reply_text(
                f"{done_line}\n\n" + _SETUP_PROMPTS[field].strip(),
                parse_mode="Markdown",
            )
            return
    context.user_data.pop("setup_flow", None)
    await update.message.reply_text(
        done_line, parse_mode="Markdown", reply_markup=_bar(user)
    )
    await animated_reply(
        update.message,
        ["🎉", ALL_SET_TEXT.strip()],
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )
    await send_promo(context, user_id)
    # Profile is complete now — the force-join gate kicks in from here.
    await enforce_channel(update, context)


# ── Forced channel subscription gate ────────────────────────────

FORCE_JOIN_TEXT = (
    "📢 **One quick step before you start!**\n\n"
    "Join our channel to use the bot.\n"
    "Tap **📢 Join Channel** below, then press **✅ I've Joined**."
)


def force_join_link() -> str | None:
    """Public t.me link for the forced channel (or the invite link if set)."""
    if FORCE_CHANNEL_INVITE:
        return FORCE_CHANNEL_INVITE
    if not FORCE_CHANNEL:
        return None
    name = FORCE_CHANNEL.lstrip("@")
    if name.startswith("-100"):
        return None  # private channel id — set FORCE_CHANNEL_INVITE instead
    return f"https://t.me/{name}"


def force_join_required() -> bool:
    return bool(FORCE_CHANNEL) and force_join_link() is not None


# Positive channel-membership results, cached briefly so the force-join
# gate doesn't cost a Telegram API round-trip on every single message.
# Only "joined" answers are cached — a "left" answer is re-checked live,
# and pressing "✅ I've Joined" always bypasses the cache.
_MEMBER_CACHE: dict[int, tuple[float, bool]] = {}
_MEMBER_CACHE_TTL = 60.0


async def is_channel_member(context, user_id: int) -> bool:
    """True when the user follows the forced channel (or no channel is set)."""
    if not force_join_required():
        return True
    hit = _MEMBER_CACHE.get(user_id)
    if hit is not None and hit[0] > time.monotonic():
        return hit[1]
    try:
        member = await context.bot.get_chat_member(FORCE_CHANNEL, user_id)
        is_member = member.status in ("member", "administrator", "creator")
    except Exception as e:  # noqa: BLE001 — fail open, never brick the bot
        logger.warning(f"Force-join check failed for {user_id}: {e}")
        return True
    if is_member:
        _MEMBER_CACHE[user_id] = (time.monotonic() + _MEMBER_CACHE_TTL, True)
    else:
        _MEMBER_CACHE.pop(user_id, None)
    return is_member


async def enforce_channel(update, context) -> bool:
    """
    Force-join gate for every entry point (commands, buttons, messages).
    Returns True when the user may proceed; otherwise shows the join popup.

    Profile setup (name → age → city) runs FIRST: while mandatory fields
    are missing the gate waits — the join popup lands only once the
    profile is complete.
    """
    if await is_channel_member(context, update.effective_user.id):
        return True
    user = db.get_user(update.effective_user.id)
    if user and missing_profile_fields(user):
        return True
    markup = force_join_keyboard(force_join_link())
    try:
        if update.message is not None:
            await update.message.reply_text(
                FORCE_JOIN_TEXT, parse_mode="Markdown", reply_markup=markup
            )
        elif update.callback_query is not None:
            await update.callback_query.answer(
                "📢 Join our channel first, then press ✅ I've Joined.",
                show_alert=True,
            )
            await context.bot.send_message(
                chat_id=update.effective_user.id,
                text=FORCE_JOIN_TEXT,
                parse_mode="Markdown",
                reply_markup=markup,
            )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Failed to send force-join prompt: {e}")
    return False


# ── Free persistence: database backup via a Telegram channel ────

# id of the last message we uploaded + hash of the contents it contained
# ("gh_hash" tracks the GitHub target separately, so one target failing
# never blocks the other).
_BACKUP_MSG = {"id": None, "hash": None, "gh_hash": None}

# True while a channel backup exists (or may exist) that this process did NOT
# load — the upload must never replace that backup with an empty database.
_RESTORE_SKIPPED = False


def _backup_enabled() -> bool:
    return bool(BACKUP_CHANNEL) and bool(db.path)


def _backup_chat():
    """Channel id (int) or @username (str) for the backup channel."""
    if BACKUP_CHANNEL.lstrip("-").isdigit():
        return int(BACKUP_CHANNEL)
    return BACKUP_CHANNEL


# Dedicated bot instance for BACKUP_BOT_TOKEN (created once, on first use)
_dedicated_backup_bot = None


async def _get_backup_bot(main_bot):
    """The bot used for backup traffic.

    When BACKUP_BOT_TOKEN is set (a separate "backup account" bot), that bot
    is created once and used for every upload/restore/pin/delete — the main
    bot keeps serving users. Otherwise the main bot does the backups itself.
    """
    global _dedicated_backup_bot
    if not _backup_enabled() or not BACKUP_BOT_TOKEN:
        return main_bot
    if BACKUP_BOT_TOKEN == (BOT_TOKEN or ""):
        return main_bot
    if _dedicated_backup_bot is None:
        candidate = Bot(BACKUP_BOT_TOKEN)
        try:
            await candidate.initialize()
        except Exception as e:  # noqa: BLE001 — bad token must not kill startup
            logger.warning(
                f"BACKUP_BOT_TOKEN unusable ({e}) — "
                "falling back to the main bot for backups."
            )
            return main_bot
        _dedicated_backup_bot = candidate
        logger.info("Dedicated backup bot active (BACKUP_BOT_TOKEN).")
    return _dedicated_backup_bot


def _is_backup_doc(message) -> bool:
    doc = getattr(message, "document", None)
    name = getattr(doc, "file_name", None) if doc else None
    return bool(doc) and name in ("bot.db", "bot.db.backup")


def _remove_quiet(path) -> None:
    """Delete a temp/probe file if it exists — never raise."""
    if not path:
        return
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


# ── GitHub backup (online, keeps every version forever) ────────────

def _github_enabled() -> bool:
    return bool(BACKUP_GITHUB_REPO and BACKUP_GITHUB_TOKEN and db.path)


def _github_headers(raw: bool = False) -> dict:
    return {
        "Authorization": f"Bearer {BACKUP_GITHUB_TOKEN}",
        "Accept": (
            "application/vnd.github.raw+json" if raw else "application/vnd.github+json"
        ),
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "telegram-chat-bot-backup",
    }


def _github_file_url() -> str:
    return (
        f"https://api.github.com/repos/{BACKUP_GITHUB_REPO}/contents/"
        f"{BACKUP_GITHUB_PATH}"
    )


async def _github_fetch_versions(limit: int) -> list[dict]:
    """Newest-first [{"sha", "date"}] of every committed bot.db version."""
    import httpx

    url = f"https://api.github.com/repos/{BACKUP_GITHUB_REPO}/commits"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            url,
            params={"path": BACKUP_GITHUB_PATH, "per_page": limit},
            headers=_github_headers(),
        )
        resp.raise_for_status()
        versions = []
        for item in resp.json():
            when = (
                item.get("commit", {}).get("committer", {}).get("date") or ""
            ).replace("Z", "+00:00")
            try:
                stamp = datetime.fromisoformat(when) if when else None
            except ValueError:
                stamp = None
            versions.append({"sha": item.get("sha", ""), "date": stamp})
        return versions


async def _github_download(sha: str):
    """Raw bytes of the snapshot committed as `sha` (None when unavailable)."""
    import httpx

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(
            _github_file_url(), params={"ref": sha}, headers=_github_headers(raw=True)
        )
        if resp.status_code != 200:
            logger.debug(f"GitHub snapshot {sha[:8]}: HTTP {resp.status_code}")
            return None
        return resp.content


async def _github_upload(data: bytes, message: str) -> bool:
    """Commit the snapshot. The previous version stays in git history forever."""
    import httpx

    url = _github_file_url()
    async with httpx.AsyncClient(timeout=60) as client:
        sha = None
        resp = await client.get(url, headers=_github_headers())
        if resp.status_code == 200:
            sha = resp.json().get("sha")
        elif resp.status_code != 404:
            logger.warning(
                f"GitHub backup: cannot read current file (HTTP {resp.status_code})"
            )
            return False
        body = {
            "message": message,
            "content": base64.b64encode(data).decode(),
        }
        if sha:
            body["sha"] = sha
        resp = await client.put(url, json=body, headers=_github_headers())
        if resp.status_code not in (200, 201):
            logger.warning(
                f"GitHub backup failed: HTTP {resp.status_code} {resp.text[:200]}"
            )
            return False
        return True


async def restore_db_from_backup(bot) -> None:
    """Download the best bot.db snapshot from GitHub and/or the channel.

    Runs on startup, before any update is handled — this is what makes a
    redeployed bot continue where it stopped (users, coins, queue, chats).

    EVERY recent snapshot (GitHub commits + channel messages) is probed and
    the one holding the MOST members wins — so a bot.db pinned by a broken
    run can never shadow the real backup, a local DB with more members than
    any snapshot is never replaced by a smaller one, and a bigger (even
    older) snapshot always beats a small fresh one.
    """
    global _RESTORE_SKIPPED
    telegram_on = _backup_enabled()
    github_on = _github_enabled()
    if not telegram_on and not github_on:
        return

    candidates: list[dict] = []  # {"label", "date", "load": coro(path) -> bool}
    telegram_failed = False
    github_failed = False

    # ── source 1: every committed version in the GitHub repo ──────
    if github_on:
        try:
            versions = await _github_fetch_versions(BACKUP_GITHUB_HISTORY)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"GitHub backups unreachable: {e}")
            github_failed = True
            versions = []
        for ver in versions:

            async def _gh_load(path, sha=ver["sha"]):
                try:
                    data = await _github_download(sha)
                except Exception as e:  # noqa: BLE001
                    logger.debug(f"GitHub snapshot {sha[:8]} unreadable: {e}")
                    return False
                if not data:
                    return False
                with open(path, "wb") as fh:
                    fh.write(data)
                return True

            candidates.append(
                {
                    "label": f"github:{ver['sha'][:8]}",
                    "date": ver.get("date"),
                    "source": "github",
                    "load": _gh_load,
                }
            )

    # ── source 2: every bot.db message in the channel ─────────────
    chat = None
    if telegram_on:
        try:
            chat = await bot.get_chat(_backup_chat())
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"BACKUP_CHANNEL not usable ({e}) — "
                "is the bot an ADMIN of that channel?"
            )
            telegram_failed = True

    seen: set = set()

    def _add_channel_candidate(msg) -> None:
        if not _is_backup_doc(msg):
            return
        mid = getattr(msg, "message_id", None)
        if mid is not None:
            if mid in seen:
                return
            seen.add(mid)

        async def _tg_load(path, message=msg):
            try:
                file = await message.document.get_file()
                await file.download_to_drive(path)
                return True
            except Exception as e:  # noqa: BLE001
                logger.debug(f"Channel snapshot unreadable: {e}")
                return False

        candidates.append(
            {
                "label": f"telegram:{mid}",
                "date": getattr(msg, "date", None),
                "source": "channel",
                "load": _tg_load,
            }
        )

    if chat is not None:
        history = getattr(bot, "get_chat_history", None)
        if history is not None:
            try:
                async for msg in history(_backup_chat(), limit=BACKUP_SCAN_LIMIT):
                    _add_channel_candidate(msg)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Could not scan backup channel history: {e}")
                telegram_failed = True
        else:
            logger.warning("This python-telegram-bot version has no get_chat_history")
        pinned = getattr(chat, "pinned_message", None)
        if pinned is not None:
            _add_channel_candidate(pinned)

    source_failed = telegram_failed or github_failed

    if not candidates:
        if source_failed and not db.users:
            logger.error(
                "Backup sources unreachable and the local DB is empty — "
                "uploads paused until a restore succeeds (see warnings above)."
            )
            _RESTORE_SKIPPED = True
        else:
            logger.info("No database backup found yet — starting fresh.")
            _RESTORE_SKIPPED = False
        return

    # ── probe candidates: how many members does each one hold? ────
    best, best_count, best_path = None, -1, None
    for i, cand in enumerate(candidates):
        probe = f"{db.path}.probe{i}"
        count = -1
        try:
            if await cand["load"](probe):
                conn = sqlite3.connect(probe)
                try:
                    count = int(
                        conn.execute("select count(*) from users").fetchone()[0]
                    )
                finally:
                    conn.close()
        except Exception as e:  # noqa: BLE001 — skip an unreadable snapshot
            logger.debug(f"Backup candidate {i} ({cand['label']}) unreadable: {e}")
            count = -1
        if count > best_count:
            _remove_quiet(best_path)
            best, best_count, best_path = cand, count, probe
        else:
            _remove_quiet(probe)

    if best_path is None:
        logger.error("Backups were found but none could be read.")
        _RESTORE_SKIPPED = not bool(db.users)
        return

    # ── decide: does the snapshot beat what we already have? ──────
    if db.users:
        if best_count < len(db.users):
            logger.info(
                f"Backup holds {best_count} members, local has "
                f"{len(db.users)} — keeping local."
            )
            _remove_quiet(best_path)
            _RESTORE_SKIPPED = False
            return
        if best_count == len(db.users):
            # Same members: only a NEWER snapshot beats the local file.
            # (A freshly created file always has a new mtime, so this check
            # only ever applies to a DB that already holds members.)
            local_mtime = (
                os.path.getmtime(db.path) if os.path.exists(db.path) else 0
            )
            when = best.get("date")
            if when is not None and when.timestamp() <= local_mtime:
                logger.info(
                    "Local DB is newer than the backup — keeping local."
                )
                _remove_quiet(best_path)
                _RESTORE_SKIPPED = False
                return
        # More members in the snapshot → restore it no matter the dates:
        # this is what recovers a bot that was started from zero.
    else:
        if best_count <= 0:
            logger.info("No backup with members found — starting fresh.")
            _remove_quiet(best_path)
            _RESTORE_SKIPPED = False
            return

    try:
        db.replace_file_with(best_path)
    except Exception as e:  # noqa: BLE001 — never kill startup over this
        logger.error(f"❌ Database restore failed: {e}")
        _remove_quiet(best_path)
        _RESTORE_SKIPPED = not bool(db.users)
        return
    # The local DB now equals ONE of the snapshots. Mark only THAT source as
    # up to date (so it isn't re-sent) and leave the other one pending —
    # a channel restore must still seed GitHub, a GitHub restore must still
    # seed the channel. Otherwise one target could stay empty forever.
    digest = db.snapshot_hash()
    if best.get("source") == "github":
        _BACKUP_MSG["gh_hash"] = digest
        _BACKUP_MSG["hash"] = None
    else:
        _BACKUP_MSG["hash"] = digest
        _BACKUP_MSG["gh_hash"] = None
    _RESTORE_SKIPPED = False
    logger.info(
        f"✅ Database restored from {best['label']} ({len(db.users)} members)."
    )


async def _old_backup_ids(bot) -> set[int]:
    """Ids of backup docs already in the channel, NEWEST FIRST: the recent
    history, the one we sent last run and the pinned message. Only the ones
    beyond BACKUP_KEEP are deleted after an upload — the channel always
    keeps a small history so one bad upload can't destroy every copy."""
    ids: list[int] = []

    def _add(mid) -> None:
        if mid is not None and mid not in ids:
            ids.append(mid)

    history = getattr(bot, "get_chat_history", None)
    if history is not None:
        try:
            async for msg in history(_backup_chat(), limit=30):
                if _is_backup_doc(msg):
                    _add(msg.message_id)
        except Exception:  # noqa: BLE001
            pass
    _add(_BACKUP_MSG.get("id"))
    try:
        chat = await bot.get_chat(_backup_chat())
        pinned = getattr(chat, "pinned_message", None)
        if pinned is not None and _is_backup_doc(pinned):
            _add(pinned.message_id)
    except Exception:  # noqa: BLE001 — needs admin rights; history scan still runs
        pass
    return ids


async def upload_db_backup(bot) -> bool:
    """Push a fresh snapshot of the SQLite file to every online backup.

    GitHub: committed, so every previous version stays in git history
    forever. Telegram channel: keeps the last BACKUP_KEEP snapshots.
    Each target has its own change-hash, so one failing never blocks the
    other. Returns True when at least one snapshot went out.
    """
    if not (_backup_enabled() or _github_enabled()):
        return False
    if not os.path.exists(db.path):
        return False
    if _RESTORE_SKIPPED:
        # A backup source exists that this process never loaded. Uploading
        # would put an empty database in the place of the REAL one.
        logger.error(
            "Backup upload skipped — the backups were NOT restored "
            "(see startup logs). Fix the source access and restart."
        )
        return False
    try:
        db.flush()  # every pending row on disk, WAL merged into bot.db
        digest = db.snapshot_hash()
        stamp = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
        members = len(db.users)
        delivered = False

        # 1) GitHub — the previous version can never be lost
        if _github_enabled():
            if digest == _BACKUP_MSG.get("gh_hash"):
                logger.debug("GitHub backup skipped — database unchanged.")
            else:
                try:
                    with open(db.path, "rb") as fh:
                        data = fh.read()
                    if await _github_upload(
                        data, f"bot.db — {stamp} — {members} members"
                    ):
                        _BACKUP_MSG["gh_hash"] = digest
                        delivered = True
                        logger.info(
                            f"GitHub backup sent ({members} members, "
                            "previous versions kept in history)"
                        )
                    else:
                        logger.warning("GitHub backup did not go through.")
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"GitHub backup failed: {e}")

        # 2) Telegram channel — keeps the last BACKUP_KEEP snapshots
        if _backup_enabled():
            if digest == _BACKUP_MSG["hash"]:
                logger.debug("Channel backup skipped — database unchanged.")
            else:
                try:
                    old_ids = await _old_backup_ids(bot)
                    with open(db.path, "rb") as fh:
                        msg = await bot.send_document(
                            chat_id=_backup_chat(),
                            document=fh,
                            filename="bot.db",
                            caption=(
                                f"🔄 Database backup — {stamp} "
                                f"({members} members)"
                            ),
                        )
                    try:
                        await bot.pin_chat_message(
                            _backup_chat(),
                            msg.message_id,
                            disable_notification=True,
                        )
                    except Exception as e:  # noqa: BLE001 — needs admin rights
                        logger.debug(f"Could not pin the backup message: {e}")
                    for old_id in old_ids[max(BACKUP_KEEP - 1, 0):]:
                        if old_id == msg.message_id:
                            continue
                        try:
                            await bot.delete_message(_backup_chat(), old_id)
                        except Exception as e:  # noqa: BLE001 — already gone
                            logger.debug(
                                f"Could not delete old backup {old_id}: {e}"
                            )
                    _BACKUP_MSG["id"] = msg.message_id
                    _BACKUP_MSG["hash"] = digest
                    delivered = True
                    logger.info(
                        f"Channel backup sent "
                        f"(keeping the last {BACKUP_KEEP} snapshots)"
                    )
                except Exception as e:  # noqa: BLE001 — other target must live
                    logger.warning(f"Channel backup failed: {e}")

        return delivered
    except Exception as e:  # noqa: BLE001 — backup must never kill the bot
        logger.warning(f"Backup failed: {e}")
        return False


async def _backup_loop(bot) -> None:
    """Every BACKUP_INTERVAL seconds — uploads only if the DB changed."""
    while True:
        await asyncio.sleep(BACKUP_INTERVAL)
        try:
            if _RESTORE_SKIPPED:
                # A transient failure at boot must not block backups forever.
                await restore_db_from_backup(bot)
            await upload_db_backup(bot)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Backup loop error: {e}")


async def _startup_checks(application) -> None:
    """Log actionable warnings for common misconfigurations."""
    if FORCE_CHANNEL:
        try:
            me = await application.bot.get_me()
            member = await application.bot.get_chat_member(FORCE_CHANNEL, me.id)
            if member.status not in ("administrator", "creator"):
                logger.warning(
                    "FORCE_CHANNEL is set but the bot is NOT an admin there — "
                    "the join check will silently let everyone in. "
                    "Add the bot to the channel as an administrator."
                )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"FORCE_CHANNEL check failed ({e}) — make sure the bot is an "
                "ADMIN of FORCE_CHANNEL, otherwise the gate does nothing."
            )


# ── Default photo fallback (profiles without a photo) ───────────

_DEFAULT_PHOTOS_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_PHOTO_MALE = os.path.join(_DEFAULT_PHOTOS_DIR, "default_boy.jpg")
_DEFAULT_PHOTO_FEMALE = os.path.join(_DEFAULT_PHOTOS_DIR, "default_girl.png")


def default_photo_path(user) -> str:
    """
    Default profile card photo — boy photo for males, girl photo for females.
    Used when the user never set their own photo.
    """
    if user.gender == Gender.FEMALE:
        return _DEFAULT_PHOTO_FEMALE
    return _DEFAULT_PHOTO_MALE


def profile_photo_of(user) -> str:
    """The user's own photo — or the gender default when none is set."""
    return user.photo_file_id or default_photo_path(user)


def open_photo(photo_ref):
    """Open a local photo path for send_photo; pass file_ids/URLs through."""
    if photo_ref and os.path.isfile(photo_ref):
        return open(photo_ref, "rb")
    return photo_ref


async def notify_partner_found(context, user_id, partner_id):
    """
    Match card for BOTH users: one photo message that carries the
    partner's picture AND their profile info AND the chat buttons —
    never a text message with the photo bolted on underneath.

    Both cards go out concurrently so a match feels instant instead
    of waiting for the first side's animation to finish.
    """
    user = db.get_user(user_id)
    partner = db.get_user(partner_id)
    if not user or not partner:
        return
    await ensure_bot_username(context.bot)
    # Remember who was talking to whom — 🗑 Delete Messages needs it
    # after the chat (and thus user.partner_id) is gone.
    _remember_chat_partner(user_id, partner_id)
    _remember_chat_partner(partner_id, user_id)

    async def deliver(u, p):
        # MeChat-style free coin for starting a chat
        reward = db.award_match_reward(u.user_id)
        reward_line = (
            f"\n🎁 **+{reward} 🪙 free coin** for starting a chat!"
            if reward
            else ""
        )
        partner_info = (
            f"💖 **found partner for you!** Say hi 👋\n\n"
            f"{gender_emoji(p.gender)} **{md_escape(display_name(p, u))}**"
            f"{f', {p.age}' if p.age else ''}\n"
            f"📍 {p.city or p.country or 'Unknown'}\n"
            f"👁 {format_online(p)}\n"
            f"🪩 {verified_label(p)}\n"
            + ("👑 VIP member\n" if p.vip else "")
            + f"🆔 {public_id_link(p)}\n\n"
            f"Type your message below — it's forwarded anonymously."
            f"{reward_line}"
        )
        # Keep the card text so 👤 Contact Profile / ⬅️ Back can flip
        # this very message between the match card and the profile card.
        _user_data(context, u.user_id)["match_card"] = (p.user_id, partner_info)
        # Short "typing…" beat + match reveal on the photo card itself
        if ANIMATIONS_ENABLED:
            await typing_pulse(context.bot, u.user_id, times=2, interval=0.4)
        delivered = await animate_photo_card(
            context.bot,
            u.user_id,
            open_photo(profile_photo_of(p)),
            match_photo_frames(partner_info),
            reply_markup=main_reply_keyboard(secure=u.secure_chat, in_chat=True),
            parse_mode="Markdown",
            interval=0.5,
        )
        if delivered:
            return
        # No photo available — the match must still be delivered as text.
        try:
            await context.bot.send_message(
                chat_id=u.user_id,
                text=partner_info,
                parse_mode="Markdown",
                reply_markup=main_reply_keyboard(secure=u.secure_chat, in_chat=True),
            )
        except Exception as e:
            logger.warning(f"Failed to send match card to {u.user_id}: {e}")

    results = await asyncio.gather(
        deliver(user, partner), deliver(partner, user), return_exceptions=True
    )
    for r in results:
        if isinstance(r, Exception):
            logger.warning(f"Match card delivery failed: {r}")


class _MsgTarget:
    """Minimal edit target so animate_edit can 'type into' a fresh message."""

    def __init__(self, bot, chat_id):
        self._bot = bot
        self._chat_id = chat_id
        self._message_id = None

    async def edit_message_text(self, text, parse_mode=None):
        if self._message_id is None:
            msg = await self._bot.send_message(chat_id=self._chat_id, text=text)
            self._message_id = msg.message_id
        else:
            await self._bot.edit_message_text(
                chat_id=self._chat_id, message_id=self._message_id, text=text
            )


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
    name = await ensure_bot_username(context.bot)
    return f"https://t.me/{name}?start={user_id}"


def build_profile_text(user) -> str:
    bio = (user.bio or "").strip()
    bio_line = f"📝 {md_escape(bio)}\n" if bio else ""
    interests = ", ".join(user.interests) if user.interests else ""
    interests_line = f"🎯 {md_escape(interests)}\n" if interests else ""
    langs = ", ".join(user.languages) if user.languages else ""
    languages_line = f"🗣 {md_escape(langs)}\n" if langs else ""
    return PROFILE_TEMPLATE.format(
        badge="👑" if user.vip else gender_emoji(user.gender),
        name=md_escape(display_name(user, user)),
        age=user.age if user.age else "—",
        city=user.city or (user.country or "—"),
        online=format_online(user),
        public_id=public_id_link(user),
        bio_line=bio_line,
        interests_line=interests_line,
        languages_line=languages_line,
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
        theme=get_theme(user.theme).name,
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
    """Full profile card — every public field, MeChat bullet style."""
    viewer = db.get_user(viewer_id)
    lines = [
        f"{gender_emoji(target.gender)} **{md_escape(display_name(target, viewer))}**",
        f"• Name: {md_escape(display_name(target, viewer))}",
        f"• Gender: {format_gender(target.gender)}",
        f"• Age: {target.age if target.age else '—'}",
        f"• City: {target.city or 'Not set'}",
        f"• Country: {target.country or 'Not set'}",
        f"• Number of likes: {target.likes}",
        "",
        f"Currently {format_online(target)}",
        f"ID: {public_id_link(target)}",
        "",
    ]
    pref = (
        format_gender(target.preferred_gender)
        if target.preferred_gender != Gender.ANY
        else "🌍 Anyone"
    )
    if target.bio:
        lines.append(f"📝 {md_escape(target.bio[:160])}")
    if target.interests:
        lines.append(f"🎯 {md_escape(', '.join(target.interests))}")
    if target.languages:
        lines.append(f"🗣 {md_escape(', '.join(target.languages))}")
    lines.append(f"🔹 Looking for: {pref}")
    lines.append(f"🔹 Total chats: {target.total_chats}")
    lines.append(f"📇 Contacts: {len(target.contacts)}")
    if target.registered_at:
        joined = time.strftime("%d %b %Y", time.localtime(target.registered_at))
        lines.append(f"📅 Member since: {joined}")
    if target.vip:
        lines.append("👑 VIP member")
    lines.append(f"🪩 {verified_label(target)}")
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


def _remember_reply_list(context, message) -> None:
    """Same, for a list the bot sent as a plain reply (no callback query)."""
    message_id = getattr(message, "message_id", None)
    if message_id:
        context.user_data["list_message_id"] = message_id


async def show_user_card(query, context, viewer_id: int, target) -> None:
    """
    Open someone's profile as ONE photo card — picture, info and buttons
    in a single message (never a photo with the details trailing below it).
    A continuous emoji cycle plays over the card when it arrives.
    Users without a photo get their AI avatar — everyone has a photo card.
    """
    await ensure_bot_username(context.bot)
    liked = viewer_id in target.liked_by
    notify = db.get_user(viewer_id).notify_on_end
    markup = profile_view_keyboard(
        target.user_id, liked, notify,
        back=context.user_data.get("profile_back", "back_list"),
    )
    text = build_user_card(target, viewer_id)

    _remember_list_message(context, query)
    if await animate_photo_card(
        context.bot,
        viewer_id,
        open_photo(profile_photo_of(target)),
        emoji_cycle_frames(text),
        reply_markup=markup,
        parse_mode="Markdown",
        interval=0.45,
    ):
        return

    try:
        await context.bot.send_photo(
            chat_id=viewer_id,
            photo=open_photo(profile_photo_of(target)),
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
    bot_instance = getattr(message, "bot", None)
    if bot_instance is not None:
        await ensure_bot_username(bot_instance)
    markup = profile_view_keyboard(
        target.user_id,
        viewer_id in target.liked_by,
        db.get_user(viewer_id).notify_on_end,
    )
    text = build_user_card(target, viewer_id)
    if hasattr(message, "reply_photo"):
        frames = emoji_cycle_frames(text)
        try:
            if ANIMATIONS_ENABLED:
                msg = await message.reply_photo(
                    photo=open_photo(profile_photo_of(target)),
                    caption=frames[0],
                    parse_mode="Markdown",
                )
                if msg is not None:
                    await animate_message_caption(
                        msg,
                        frames[1:],
                        reply_markup=markup,
                        parse_mode="Markdown",
                    )
                return
            await message.reply_photo(
                photo=open_photo(profile_photo_of(target)),
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


def _list_badges(user) -> str:
    """🔥 VIP + ✅ verified badges shown next to names in lists."""
    return ("🔥" if user.vip else "") + ("✅" if user.verified else "")


def _plain_label(user, viewer=None) -> str:
    return (
        f"{gender_emoji(user.gender)} {_list_badges(user)}"
        f"{md_escape(display_name(user, viewer))}"
        f"{f', {user.age}' if user.age else ''}"
    )


def _nearby_pairs(viewer_id: int, radius_km: float = NEARBY_RADIUS_KM) -> list:
    pairs = []
    viewer = db.get_user(viewer_id)
    for target, dist in db.nearby_users(viewer_id, radius_km):
        pairs.append((
            f"{_plain_label(target, viewer)} • 📍 {dist:.0f} km",
            target,
        ))
    return pairs


async def send_nearby_cards(context, chat_id: int, pairs, limit: int = 5) -> None:
    """
    Reference-bot style: the nearest people arrive as photo cards with
    name/age/city/online status before the text list.
    """
    if not ANIMATIONS_ENABLED:
        return
    viewer = db.get_user(chat_id)
    for label, target in pairs[:limit]:
        dist = db.distance_km(chat_id, target.user_id)
        caption = (
            f"{_plain_label(target, viewer)}\n"
            f"📍 {dist:.0f} km away • {target.city or target.country or ''}\n"
            f"👀 {format_online(target)}\n"
            f"ID: {public_id_link(target)}"
        )
        try:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=open_photo(profile_photo_of(target)),
                caption=caption,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "👤 Open Profile", callback_data=f"view_{target.user_id}"
                    )]
                ]),
            )
        except Exception as e:  # noqa: BLE001
            logger.debug(f"nearby card for {target.user_id} skipped: {e}")


def _message_location(message):
    """Coordinates from a 📍 location or a 🏷 place (venue) message."""
    loc = getattr(message, "location", None)
    if loc is not None and getattr(loc, "latitude", None) is not None:
        return loc
    venue = getattr(message, "venue", None)
    loc = getattr(venue, "location", None) if venue is not None else None
    if loc is not None and getattr(loc, "latitude", None) is not None:
        return loc
    return None


# "12.9777, 77.5931" / a pasted maps link — coordinates typed as text.
_COORDS_RE = re.compile(r"(?<![\d.\-])(-?\d{1,2}\.\d{2,})\s*,\s*(-?\d{1,3}\.\d{2,})(?![\d.])")


def _coords_from_text(text: str):
    """(lat, lon) parsed out of a message, or None."""
    for match in _COORDS_RE.finditer(text or ""):
        lat, lon = float(match.group(1)), float(match.group(2))
        if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
            return lat, lon
    return None


def _list_markup(kind: str, pairs):
    """Back-navigation keyboard for a results list (Nearby gets 🔄 Refresh)."""
    if kind == "nearby":
        return nearby_list_keyboard(pairs)
    return user_list_keyboard(pairs)


async def prepare_nearby(context, user_id: int):
    """
    Scan for members near the viewer — 50 km first, then 500 km, then the
    whole planet — so Nearby never dead-ends on an empty tight circle.
    Sends the photo cards, remembers the list for Back and returns
    (text, reply_markup).
    """
    context.user_data["list_kind"] = "nearby"
    context.user_data["list_title"] = "📍 People near you"

    if not db.has_location(user_id):
        context.user_data["list_ids"] = []
        return (
            f"📍 **Nearby People**\n\n"
            f"Share your location to see people within {NEARBY_RADIUS_KM} km "
            f"of you.",
            share_location_keyboard(),
        )

    pairs: list = []
    title = "📍 People near you"
    previous_ids = set(context.user_data.get("list_ids") or [])
    for radius in (NEARBY_RADIUS_KM, NEARBY_WIDE_RADIUS_KM, EARTH_RADIUS_KM * 2):
        pairs = await asyncio.to_thread(_nearby_pairs, user_id, radius)
        if pairs:
            if radius == NEARBY_WIDE_RADIUS_KM:
                title = (
                    f"📍 No one within {NEARBY_RADIUS_KM} km — nearest people "
                    f"within {NEARBY_WIDE_RADIUS_KM} km"
                )
            elif radius > NEARBY_WIDE_RADIUS_KM:
                title = (
                    f"📍 No one within {NEARBY_WIDE_RADIUS_KM} km — "
                    f"nearest members anywhere"
                )
            break

    context.user_data["list_ids"] = [u.user_id for _, u in pairs]
    # 📋 Send Message to List works from Nearby too — same recipient pool.
    context.user_data["browse_ids"] = context.user_data["list_ids"]
    if not pairs:
        return (
            "📍 **No one here yet**\n\n"
            "No other member with a shared location was found.\n\n"
            "👉 Tap **📍 Share My Location** below if you haven't, then "
            "**🔄 Refresh** — anyone who shares later appears here.",
            nearby_list_keyboard([]),
        )

    # Photo cards only for people we haven't just shown (a Refresh with the
    # same neighbours shouldn't flood the chat with the same pictures).
    if set(context.user_data["list_ids"]) != previous_ids:
        await send_nearby_cards(context, user_id, pairs)
    context.user_data["list_title"] = title
    viewer = db.get_user(user_id)
    return (
        _list_text(title, pairs, viewer, kind="nearby"),
        nearby_list_keyboard(pairs),
    )


def _pairs_from_ids(viewer_id: int, ids, kind: str) -> list:
    pairs = []
    viewer = db.get_user(viewer_id)
    for uid in ids:
        user = db.get_user(uid)
        if not user:
            continue
        if kind == "nearby":
            dist = db.distance_km(viewer_id, uid)
            prefix = f"📍 {dist:.0f} km • " if dist is not None else "📍 "
            pairs.append((f"{prefix}{_plain_label(user, viewer)}", user))
        else:
            pairs.append((_plain_label(user, viewer), user))
    return pairs


def _nearby_entry(target, viewer=None) -> str:
    """One 📍 Nearby row — name/ID, place + distance, last-seen activity."""
    dist = db.distance_km(viewer.user_id, target.user_id) if viewer else None
    if target.country and target.city:
        place = f"{target.country} ({target.city})"
    else:
        place = target.city or target.country or "Not set"
    return (
        f"{gender_emoji(target.gender)} {_list_badges(target)}"
        f"**{md_escape(display_name(target, viewer))}**"
        f"{f', {target.age}' if target.age else ''} • {public_id_link(target)}\n"
        f"📍 {md_escape(place)}"
        + (f" • {dist:.0f} km away" if dist is not None else "")
        + f"\n{activity_line(target)}\n"
        f"{'〰️' * 8}"
    )


def _list_text(title: str, pairs, viewer=None, kind: str = "plain") -> str:
    if not pairs:
        return f"{title}\n\nNo one here right now."
    header = f"{title}\n\n👥 {len(pairs)} found — tap one to open their profile:"
    if kind == "nearby" and viewer is not None:
        body = "\n\n".join(_nearby_entry(user, viewer) for _, user in pairs)
        return f"{header}\n\n{body}"
    return header


def _browse_entry(target, viewer=None) -> str:
    """One 🎉 Browse People entry, formatted like the reference bot."""
    place = ", ".join(p for p in (target.country, target.city) if p) or "Not set"
    return (
        f"{gender_emoji(target.gender)} {_list_badges(target)}"
        f"**{md_escape(display_name(target, viewer))}**"
        f"{f', {target.age}' if target.age else ''} • {public_id_link(target, public_id_slug(target))}\n"
        f"📍 {place}\n"
        f"👀 {format_online(target)}\n"
        f"{'〰️' * 8}"
    )


def _browse_text(users, total: int, viewer=None) -> str:
    if not users:
        return "🎉 **Browse People**\n\nNo one else is here yet — check back soon!"
    header = f"🎉 **People online** ({total})"
    body = "\n\n".join(_browse_entry(u, viewer) for u in users)
    return f"{header}\n\n{body}\n\nShowing 1–{len(users)} of {total}."


def _browse_state(context, user_id: int):
    """(text, markup) for the current Browse People page."""
    ids = context.user_data.get("browse_ids", [])
    users = [u for u in (db.get_user(i) for i in ids) if u]
    total = context.user_data.get("browse_total", len(users))
    has_more = len(users) < total
    viewer = db.get_user(user_id)
    pairs = [(_plain_label(u, viewer), u) for u in users]
    return _browse_text(users, total, viewer), browse_keyboard(has_more, pairs)


async def _render_swipe(query, context, viewer_id: int, index: int) -> None:
    """✨ View Profiles by Swiping — one card at a time."""
    ids = context.user_data.get("swipe_ids", [])
    target = db.get_user(ids[index])
    if not target:
        await query.answer("That account no longer exists.", show_alert=True)
        return
    text = f"{_browse_entry(target, db.get_user(viewer_id))}\n\nProfile {index + 1} of {len(ids)}"
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
            text=f"🏆 A {kind} just viewed your profile 👀🔥",
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
            await _safe_send(
                context, uid, "🔔 Your chat has ended.",
                reply_markup=main_menu_keyboard(),
            )


# ── 🗑 chat log: remember the messages the bot put in a chat so the
#    "Delete Messages" button can wipe them (30 min after the chat ends).
#    Telegram only lets a bot delete its OWN messages, and what you send
#    lands in the partner's chat as a bot message — so we log there and
#    tag every entry with the original sender. ─────────────────────

CHAT_DELETE_WINDOW = 30 * 60          # seconds after the chat ends
_CHAT_LOGS: dict[int, dict] = {}      # user_id -> log (see _chat_log)
_CHAT_LOG_USERS = 4                   # most recent chats kept per user


def _chat_log(chat_id: int) -> dict:
    log = _CHAT_LOGS.get(chat_id)
    if log is None:
        log = _CHAT_LOGS[chat_id] = {"partner": None, "ids": [], "ended_at": None}
        while len(_CHAT_LOGS) > _CHAT_LOG_USERS * 8:
            _CHAT_LOGS.pop(next(iter(_CHAT_LOGS)))
    return log


def _track_chat_msg(chat_id: int, message, src=None) -> None:
    """Remember a message the bot sent into `chat_id` (`src` = the user
    whose message it was, None for the bot's own notices)."""
    mid = getattr(message, "message_id", None)
    if mid is None:
        return
    log = _chat_log(chat_id)
    if not any(e["mid"] == mid for e in log["ids"]):
        log["ids"].append({"mid": mid, "src": src})
        del log["ids"][:-120]


def _remember_chat_partner(chat_id: int, partner_id) -> None:
    log = _chat_log(chat_id)
    log["partner"] = partner_id
    log["ended_at"] = None


def _stamp_chat_end(chat_id: int) -> None:
    if chat_id in _CHAT_LOGS:
        _CHAT_LOGS[chat_id]["ended_at"] = time.time()


async def _safe_send(context, chat_id, text, **kwargs):
    """Send a message without ever letting a dead chat break the flow."""
    try:
        return await context.bot.send_message(chat_id=chat_id, text=text, **kwargs)
    except Forbidden as e:
        logger.debug(f"cannot reach {chat_id}: {e}")
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Failed to message {chat_id}: {e}")
        return None


def _delete_slug(user) -> str:
    """/delet_messages_<slug> token for a user (the ID without the prefix)."""
    slug = public_id_slug(user)
    return slug[5:] if slug.startswith("user_") else slug


async def _send_end_block(context, uid, *, notice, offer_choice: bool) -> None:
    """MeChat's chat-end sequence: notice → 🗑 delete hint → 🎲 choose menu.

    With a choice on the way the two preceding messages stay clean (the
    persistent bar under the message field is all the navigation needed).
    The chat is over now, so one of the messages carries the bar flipped
    back to the discovery buttons — a reply keyboard only changes when a
    message carries it.
    """
    quiet = None if offer_choice else main_menu_keyboard()
    me = db.get_user(uid)
    bar = _bar(me) if me else None
    await _safe_send(context, uid, notice, reply_markup=quiet or bar)
    if me:
        await _safe_send(
            context, uid, DELETE_HINT_TEXT.format(slug=_delete_slug(me)),
            reply_markup=bar if quiet else None,
        )
    if offer_choice:
        await _safe_send(
            context, uid, SEARCH_CHOICE_TEXT,
            parse_mode="Markdown",
            reply_markup=search_choice_keyboard(),
        )


async def close_chat(
    context,
    user_id: int,
    leaver_notice: str = "👋 You left the chat.",
    *,
    offer_choice: bool = True,
) -> None:
    """
    End a chat for user_id, tell both sides in the reference bot's wording
    (notice → 🗑 delete hint → 🎲 choose who to chat with next) and honour
    the 🔔 "notify me when chat ends" toggle.
    """
    partner_id = db.end_chat(user_id)
    me = db.get_user(user_id)
    _stamp_chat_end(user_id)
    if partner_id:
        _stamp_chat_end(partner_id)

    await _send_end_block(
        context, user_id, notice=leaver_notice, offer_choice=offer_choice
    )
    if partner_id:
        who = format_public_id(me) if me else "your partner"
        await _send_end_block(
            context,
            partner_id,
            notice=CHAT_ENDED_TEXT.format(who=who),
            offer_choice=offer_choice,
        )
    await _ping_chat_end(context, user_id, partner_id)


async def begin_search(
    context, user_id: int, search_pref: Gender, target=None
):
    """
    Start a search with the given per-search filter.
    Charges coins for 🕺 Guy and 👩 Girl searches (🎲 Random is free, VIP
    members never pay). When `target` (a Message or CallbackQuery) is given
    and animations are on, the "matching you with a partner" animation runs
    THERE — continuously, until a match lands — and (None, None, None) is
    returned so the caller doesn't send a duplicate message.
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

    pending = profile_setup_reply(context, user)
    if pending:
        return pending

    # 🎁 MANDATORY daily check-in — a friendly nudge before anything else.
    if user.last_checkin != bot_today():
        return (
            "🎁 **Daily Check-in required**\n\n"
            "You must claim your Daily Check-in first — it's how you earn "
            f"**{DAILY_CHECKIN_COINS} 🪙** and it unlocks today's coins, "
            "points and match rewards.\n\n"
            "Tap 🎁 Daily Check-in in the main menu, then **Claim**.",
            checkin_keyboard(claimed_today=False),
            "Markdown",
        )

    if user.state == ChatState.CHATTING:
        # A stale 🎲 Choose-menu tap while talking: leave the chat first,
        # then hand back the choice — never the "already in a chat" wall.
        await close_chat(
            context, user_id, leaver_notice="👋 You left the chat.",
            offer_choice=False,
        )
        return SEARCH_CHOICE_TEXT, search_choice_keyboard(), "Markdown"

    if user.state == ChatState.SEARCHING:
        return "⏳ You're already searching for a partner...", searching_keyboard(), None

    # 🕺 Guy and 👩 Girl searches cost coins — 🎲 Random stays free.
    charged = 0
    charge_label = ""
    if search_pref in (Gender.MALE, Gender.FEMALE) and not user.vip:
        cost = GUY_SEARCH_COST if search_pref == Gender.MALE else GIRL_SEARCH_COST
        charge_label = "Guy" if search_pref == Gender.MALE else "Girl"
        if not db.spend_coins(user_id, cost):
            want = "🕺 a Guy" if charge_label == "Guy" else "👩 a Girl"
            return (
                f"🪙 **Not enough Coins!**\n\n"
                f"Searching for {want} costs **{cost} 🪙 per search**.\n"
                f"Invite friends (/link) or buy Coins (/credit) to earn more.",
                credit_keyboard(),
                "Markdown",
            )
        charged = cost

    def _charge_line() -> str:
        if not charged:
            return ""
        balance = db.get_user(user_id).coins
        return f"\n\n🪙 -{charged} ({charge_label} search) | Balance: {balance}"

    db.add_to_queue(user_id, search_pref=search_pref)
    match_id = await asyncio.to_thread(db.find_match, user_id)

    if match_id and db.pair_users(user_id, match_id):
        await notify_partner_found(context, user_id, match_id)
        # Resolve whatever "Searching…" message the caller is holding —
        # otherwise a stale search frame keeps claiming a search is running.
        return "🎉 Partner found! Connecting..." + _charge_line(), None, None

    # Continuous matching animation — cycles until a match lands.
    if target is not None and ANIMATIONS_ENABLED:
        def _check():
            found = db.find_match(user_id)
            if found and db.pair_users(user_id, found):
                return found
            return None

        def _cancelled():
            me = db.get_user(user_id)
            return me is None or me.state != ChatState.SEARCHING

        found = await animate_search(
            context,
            user_id,
            _check,
            queue_size_fn=lambda: db.searching_count,
            target=target,
            interval=1.0,
            stop_check=_cancelled,
            reply_markup=searching_keyboard(),
        )
        if found:
            await notify_partner_found(context, user_id, found)
            return "🎉 Partner found! Connecting..." + _charge_line(), None, None
        # The loop stopped without a match: the search was cancelled, or a
        # chat request matched this user while the frames were running.
        # Replace the frame so nothing keeps showing a search that is over —
        # but only if nothing else (a fresh search) took the message over.
        me = db.get_user(user_id)
        final_text = None
        if me is not None and me.state == ChatState.IDLE:
            if me.search_started_at:
                # The queue sweep expired this search — distinct from a
                # user-initiated cancel (which clears the stamp).
                final_text = "⌛ Search timed out — no partner found yet."
            else:
                final_text = "❌ Search cancelled."
            final_text += _charge_line()
        elif me is not None and me.state == ChatState.CHATTING:
            final_text = "🎉 Partner found! Check your latest message."
        if final_text:
            try:
                if hasattr(target, "edit_message_text"):
                    await target.edit_message_text(
                        final_text, reply_markup=main_menu_keyboard()
                    )
                elif hasattr(target, "edit_text"):
                    await target.edit_text(
                        final_text, reply_markup=main_menu_keyboard()
                    )
            except Exception as e:  # noqa: BLE001
                logger.debug(f"final search frame skipped: {e}")
        return None, None, None

    text = SEARCHING_TEXT.format(count=db.searching_count)
    return text + _charge_line(), searching_keyboard(), "Markdown"


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
    await close_chat(
        context, reporter_id,
        leaver_notice="👋 You left the chat.",
        offer_choice=False,
    )

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
#  🎁 DAILY CHECK-IN · 🏆 LEADERBOARD · 🎮 GAMES · 🎨 THEMES
#  🟢 AVAILABILITY · 🛡️ PRIVACY · 👤 PROFILE EXTRAS
# ═══════════════════════════════════════════════════════════════════

CHECKIN_TEXT = (
    "🎁 **Daily Check-in**\n\n"
    "Tap the button below to claim **{coins} 🪙** — once per calendar day.\n"
    "💰 Your balance: **{balance} 🪙**\n\n"
    "💡 Come back every day to keep your coin stash growing!"
)

CHECKIN_CLAIMED_TEXT = (
    "✅ **Check-in claimed!**\n\n"
    "🪙 +{earned} coins\n"
    "💰 Balance: **{balance} 🪙**\n\n"
    "Come back tomorrow for another reward!"
)

CHECKIN_ALREADY_TEXT = (
    "⏳ **Already checked in today!**\n\n"
    "You've claimed your {coins} 🪙 for today.\n"
    "💰 Balance: **{balance} 🪙**\n"
    "Come back tomorrow for more!"
)

LEADERBOARD_TEXT = (
    "🏆 **Weekly Leaderboard** ({week})\n\n"
    "{top_block}\n"
    "🪙 Your points: **{mine}**\n\n"
    "🎁 **Weekly rewards** (top 3 only):\n"
    "🥇 1st — {r1} 🪙\n"
    "🥈 2nd — {r2} 🪙\n"
    "🥉 3rd — {r3} 🪙\n"
    "Everyone else: 0 coins.\n\n"
    "Resets every week — good luck!"
)

LB_HOW_TEXT = (
    "❓ **How leaderboard points work**\n\n"
    "🎁 **Daily Check-in is required first** — until you claim it, you "
    f"earn **no points and no coins** today. It also pays **{DAILY_CHECKIN_COINS} 🪙**.\n\n"
    "You earn points from real activity (daily caps stop farming):\n"
    f"• 💬 Completed chats: +2 per chat (cap {POINT_CAPS['chat']}/day)\n"
    f"• 💬 Messages in chats: +1 per 5 messages (cap {POINT_CAPS['message']}/day)\n"
    f"• 🎮 Mini-games played: +1 per game (cap {POINT_CAPS['game']}/day)\n"
    f"• 🎁 Daily check-ins: +1 (cap {POINT_CAPS['checkin']}/day)\n"
    f"• ❤️ Unique likes received: +1 (cap {POINT_CAPS['like']}/day)\n\n"
    "🚫 Spam, fake accounts and exploits earn nothing — points are capped "
    "per category per day, and only legitimate activity counts.\n\n"
    "🏆 Only the **top 3** each week get coins (6 / 4 / 2)."
)

SAFETY_TEXT = (
    "🛡️ **Privacy & Safety**\n\n"
    "• 🚫 **Block** anyone from their profile — you'll never be matched again\n"
    "• 🚩 **Report** bad behaviour — 5 unique reports restrict an account\n"
    "• 🔒 **Secure Chat** toggles forwarding protection mid-chat\n"
    "• 🎂 Age safety: Direct Messages require both people to be 16+, and "
    "adults can't DM minors\n"
    "• 🔐 Your @username is NEVER shown to other users\n"
    "• ⚫ **Invisible** hides you from lists & matching (auto-resets after "
    f"{AVAILABILITY_TTL // 3600}h)\n"
    "• 🗑 Delete your chat messages within 30 minutes after a chat ends"
)


def _available_label(user) -> str:
    return {
        Availability.READY: "🟢",
        Availability.BUSY: "🟡",
        Availability.INVISIBLE: "⚫",
    }.get(getattr(user, "availability", Availability.READY), "🟢")


async def handle_checkin(update, context, query, user) -> None:
    """🎁 Daily login reward — 1 coin per calendar day, spam-proof."""
    today = bot_today()
    if user.last_checkin == today:
        await safe_edit(
            query,
            CHECKIN_ALREADY_TEXT.format(
                coins=DAILY_CHECKIN_COINS, balance=user.coins
            ),
            parse_mode="Markdown",
            reply_markup=checkin_keyboard(claimed_today=True),
        )
        return
    await safe_edit(
        query,
        CHECKIN_TEXT.format(coins=DAILY_CHECKIN_COINS, balance=user.coins),
        parse_mode="Markdown",
        reply_markup=checkin_keyboard(claimed_today=False),
    )


async def handle_checkin_claim(update, context, query, user) -> None:
    """Atomic claim — Database guards against double-claims per day."""
    claimed, earned, balance = db.claim_daily_checkin(user.user_id)
    tomorrow = bot_now().strftime("%d %b")
    if claimed:
        await safe_edit(
            query,
            CHECKIN_CLAIMED_TEXT.format(
                earned=earned, balance=balance, tomorrow=tomorrow
            ),
            parse_mode="Markdown",
            reply_markup=checkin_keyboard(claimed_today=True),
        )
    else:
        await safe_edit(
            query,
            CHECKIN_ALREADY_TEXT.format(
                coins=DAILY_CHECKIN_COINS, balance=balance
            ),
            parse_mode="Markdown",
            reply_markup=checkin_keyboard(claimed_today=True),
        )


def _lb_top_block(entries) -> str:
    if not entries:
        return "_No points scored yet this week — be the first!_"
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (u, pts) in enumerate(entries):
        medal = medals[i] if i < 3 else f"{i + 1}."
        lines.append(f"{medal} {md_escape(display_name(u))} — **{pts}** pts")
    return "\n".join(lines)


async def handle_leaderboard(update, context, query, user) -> None:
    db.expire_stale_availability()
    entries = db.leaderboard_top(10)
    r1 = WEEKLY_REWARD_COINS.get(1, 6)
    r2 = WEEKLY_REWARD_COINS.get(2, 4)
    r3 = WEEKLY_REWARD_COINS.get(3, 2)
    await safe_edit(
        query,
        LEADERBOARD_TEXT.format(
            week=current_week_id(),
            top_block=_lb_top_block(entries),
            mine=db.weekly_points_of(user.user_id),
            r1=r1, r2=r2, r3=r3,
        ),
        parse_mode="Markdown",
        reply_markup=leaderboard_keyboard(),
    )


async def handle_lb_history(update, context, query, user) -> None:
    history = db.weekly_history(3)
    if not history:
        await safe_edit(
            query,
            "📜 **Previous weeks**\n\nNo completed weeks yet — the first "
            "rewards land after the current week ends.",
            parse_mode="Markdown",
            reply_markup=leaderboard_keyboard(),
        )
        return
    lines = ["📜 **Previous weeks**", ""]
    medals = ["🥇", "🥈", "🥉"]
    for entry in history:
        lines.append(f"**{entry['week']}**")
        for res in entry.get("results", []):
            medal = medals[res["rank"] - 1] if res["rank"] <= 3 else f"{res['rank']}."
            who = db.get_user(res["user_id"])
            name = md_escape(display_name(who)) if who else f"ID {res['user_id']}"
            lines.append(
                f"{medal} {name} — {res['points']} pts → +{res['coins']} 🪙"
            )
        lines.append("")
    await safe_edit(
        query,
        "\n".join(lines)[:3500],
        parse_mode="Markdown",
        reply_markup=leaderboard_keyboard(),
    )


# ── 🎮 Mini-games ────────────────────────────────────────────────

def _game_session(context) -> dict:
    return context.user_data.get("game") or {}


def _store_game(context, session: dict) -> None:
    context.user_data["game"] = session


async def _render_game_card(query, context, user, session: dict, footer: str = "") -> None:
    """Draw the current game state as one message with Skip/Replay/Exit."""
    game_id = session.get("game", "")
    spec = games_mod.GAME_DEFS.get(game_id, {})
    title = spec.get("title", "🎮 Game")
    kind = session.get("kind")

    if session.get("done") and kind != "truthdare":
        text = (
            f"{title}\n\n"
            f"🏁 **Game over!**\n{games_mod.score_line(session)}\n\n"
            f"Tap 🔁 Replay to play again or ❌ Exit to leave."
        )
        await safe_edit(query, text, parse_mode="Markdown",
                        reply_markup=game_controls_keyboard())
        return

    extra = []
    if kind == "choice2":
        q = games_mod.current_question(session)
        if q is None:
            session["done"] = True
            await _render_game_card(query, context, user, session, footer)
            return
        text = (
            f"{title}\n\n"
            f"**{q['a']}**\n"
            f"     — or —    \n"
            f"**{q['b']}**\n\n"
            f"{games_mod.score_line(session)}"
        )
        extra = [
            [
                InlineKeyboardButton("🅰 A", callback_data="gopt_0"),
                InlineKeyboardButton("🅱 B", callback_data="gopt_1"),
            ]
        ]
    elif kind == "truthdare":
        prompt = session.get("prompt")
        if not prompt:
            text = f"{title}\n\nPick **Truth** or **Dare** to begin! 🎭"
        else:
            text = f"{title}\n\n{prompt}\n\n{games_mod.score_line(session)}"
        extra = [
            [
                InlineKeyboardButton("🤫 Truth", callback_data="gopt_truth"),
                InlineKeyboardButton("⚡ Dare", callback_data="gopt_dare"),
            ]
        ]
    elif kind in ("quiz", "emoji"):
        q = games_mod.current_question(session)
        if q is None:
            session["done"] = True
            await _render_game_card(query, context, user, session, footer)
            return
        emojis = games_mod._q_get(q, "emojis")
        question_line = (
            f"{emojis}\n\nWhat does this mean? 😅"
            if emojis
            else str(games_mod._q_get(q, "q", ""))
        )
        options = games_mod._q_get(q, "options", [])
        text = (
            f"{title}\n\n"
            f"Q{session['round'] + 1}/{session.get('total', '?')}\n\n"
            f"{question_line}\n\n"
            f"{games_mod.score_line(session)}"
        )
        rows = [
            [InlineKeyboardButton(
                f"{chr(65 + i)}️⃣ {str(opt)[:40]}",
                callback_data=f"gopt_{i}",
            )]
            for i, opt in enumerate(options)
        ]
        extra = rows
    elif kind == "yesno":
        q = games_mod.current_question(session)
        if q is None:
            session["done"] = True
            await _render_game_card(query, context, user, session, footer)
            return
        text = (
            f"{title}\n\n"
            f"Q{session['round'] + 1}/{session.get('total', '?')}\n\n"
            f"{q}\n\n{games_mod.score_line(session)}"
        )
        extra = [
            [
                InlineKeyboardButton("✅ Yes", callback_data="gopt_1"),
                InlineKeyboardButton("❌ No", callback_data="gopt_0"),
            ]
        ]
    elif kind == "number":
        hint = session.get("feedback") or "I'm thinking of a number… 🤔"
        text = (
            f"{title}\n\n"
            f"{hint}\n\n"
            f"Range: {session.get('low', 1)}–{session.get('high', 100)}\n"
            f"{games_mod.score_line(session)}\n\n"
            f"Send your guess as a number, or use the quick buttons."
        )
        last = session.get("last_guess") or 50
        extra = [
            [
                InlineKeyboardButton("⬇️ Lower", callback_data="gnum_lo"),
                InlineKeyboardButton("🎯 It's this!", callback_data="gnum_hit"),
                InlineKeyboardButton("⬆️ Higher", callback_data="gnum_hi"),
            ]
        ]
        quick = []
        for delta in (-10, -5, 5, 10):
            g = max(1, min(100, last + delta))
            quick.append(InlineKeyboardButton(f"Try {g}", callback_data=f"gnum_{g}"))
        extra.append(quick)
    else:
        text = f"{title}\n\nComing soon!"

    if footer:
        text += f"\n\n{footer}"
    await safe_edit(query, text, parse_mode="Markdown",
                    reply_markup=game_controls_keyboard(extra))


async def handle_game_start(update, context, query, user, game_id: str) -> None:
    session = games_mod.new_game(game_id)
    if not session:
        await query.answer("Unknown game.", show_alert=True)
        return
    _store_game(context, session)
    await _render_game_card(query, context, user, session)


async def handle_game_option(update, context, query, user, choice: str) -> None:
    session = _game_session(context)
    if not session or session.get("done"):
        await query.answer("Start a game first 🎮", show_alert=True)
        return
    kind = session.get("kind")

    if kind == "truthdare":
        session["prompt"] = games_mod.pick_truth_or_dare(session, choice == "truth")
    elif kind in ("quiz", "emoji"):
        correct, fact = games_mod.answer_quiz(session, int(choice))
        footer = ("✅ Correct! " if correct else "❌ Not quite! ") + fact
        _store_game(context, session)
        if session.get("done"):
            db.add_weekly_points(user.user_id, 1, "game")
        await _render_game_card(query, context, user, session, footer=footer[:250])
        return
    elif kind == "yesno":
        games_mod.answer_yesno(session, choice == "1")
    elif kind == "choice2":
        session["round"] += 1
        session["score"] += 1
        total = len(session.get("questions", []))
        if session["round"] >= total:
            session["done"] = True
            db.add_weekly_points(user.user_id, 1, "game")
        _store_game(context, session)
        await _render_game_card(query, context, user, session, footer="Fun pick! 🎉")
        return

    _store_game(context, session)
    await _render_game_card(query, context, user, session)


async def handle_game_number(update, context, query, user, action: str) -> None:
    session = _game_session(context)
    if not session or session.get("kind") != "number":
        await query.answer("Start Guess the Number first 🔢", show_alert=True)
        return
    if session.get("done"):
        await query.answer("Game over — tap 🔁 Replay.", show_alert=True)
        return
    last = session.get("last_guess") or 50
    if action == "hit":
        guess = last
    elif action == "hi":
        guess = min(100, last + 5)
    elif action == "lo":
        guess = max(1, last - 5)
    else:
        try:
            guess = int(action)
        except ValueError:
            return
        guess = max(1, min(100, guess))
    feedback = games_mod.number_feedback(session, guess)
    session["feedback"] = feedback
    _store_game(context, session)
    if session.get("done"):
        db.add_weekly_points(user.user_id, 1, "game")
    await _render_game_card(query, context, user, session)


async def handle_game_skip(update, context, query, user) -> None:
    session = _game_session(context)
    if not session:
        await query.answer("No game running.", show_alert=True)
        return
    if session.get("kind") == "truthdare":
        session["prompt"] = None
    games_mod.skip_round(session)
    _store_game(context, session)
    await _render_game_card(query, context, user, session, footer="⏭ Skipped.")


async def handle_game_replay(update, context, query, user) -> None:
    session = _game_session(context)
    game_id = session.get("game") if session else None
    if not game_id:
        await query.answer("No game to replay.", show_alert=True)
        return
    await handle_game_start(update, context, query, user, game_id)


async def handle_game_exit(update, context, query, user) -> None:
    context.user_data.pop("game", None)
    await safe_edit(query, "👋 Game closed.", reply_markup=games_menu_keyboard())


# ── 🎨 Themes ────────────────────────────────────────────────────

async def handle_theme_menu(update, context, query, user) -> None:
    unlocked = set(user.unlocked_themes or []) | {"default"}
    await safe_edit(
        query,
        f"🎨 **Customize Theme**\n\n"
        f"💰 Your coins: **{user.coins} 🪙**\n"
        f"🎭 Active: **{get_theme(user.theme).name}**\n\n"
        f"Unlock cosmetic themes with coins — they decorate your cards "
        f"and menus. Tap one to equip or buy it.",
        parse_mode="Markdown",
        reply_markup=theme_keyboard(
            list(THEMES.values()), user.theme, unlocked
        ),
    )


async def handle_theme_buy(update, context, query, user, theme_id: str) -> None:
    theme = THEMES.get(theme_id)
    if not theme:
        await query.answer("Unknown theme.", show_alert=True)
        return
    ok, msg = db.unlock_theme(user.user_id, theme_id, theme.cost)
    if ok:
        await query.answer(f"🎨 {theme.name} unlocked & equipped!")
        await handle_theme_menu(update, context, query, db.get_user(user.user_id))
        return
    if msg == "not_enough":
        await query.answer(
            f"🪙 Not enough coins! {theme.name} costs {theme.cost} 🪙.",
            show_alert=True,
        )
        return
    await query.answer(msg, show_alert=True)


async def handle_theme_equip(update, context, query, user, theme_id: str) -> None:
    if db.equip_theme(user.user_id, theme_id):
        await query.answer(f"🎨 {get_theme(theme_id).name} equipped!")
        await handle_theme_menu(update, context, query, db.get_user(user.user_id))
    else:
        await query.answer("Buy that theme first.", show_alert=True)


# ── 🟢 Availability ──────────────────────────────────────────────

AVAILABILITY_SET_TEXT = {
    Availability.READY: "🟢 Ready to Chat",
    Availability.BUSY: "🟡 Busy",
    Availability.INVISIBLE: "⚫ Invisible",
}


async def handle_availability_menu(update, context, query, user) -> None:
    current = getattr(user, "availability", Availability.READY)
    await safe_edit(
        query,
        f"🟢 **Your availability**\n\n"
        f"Current: {_available_label(user)} **{current.value.title()}**\n\n"
        f"• 🟢 **Ready to Chat** — shown first in matching & the Ready list\n"
        f"• 🟡 **Busy** — deprioritised until you're free\n"
        f"• ⚫ **Invisible** — hidden from lists & random matching\n\n"
        f"⏳ Stale statuses automatically expire back to 🟢 Ready after "
        f"{AVAILABILITY_TTL // 3600} hours.",
        parse_mode="Markdown",
        reply_markup=availability_keyboard(current.value),
    )


async def handle_availability_set(update, context, query, user, value: str) -> None:
    try:
        avail = Availability(value)
    except ValueError:
        return
    db.set_availability(user.user_id, avail)
    await query.answer(AVAILABILITY_SET_TEXT[avail])
    await handle_availability_menu(
        update, context, query, db.get_user(user.user_id)
    )


# ── 🧠 Quiz Battle (2-player) ────────────────────────────────────

async def handle_battle_challenge(update, context, query, user) -> None:
    """Challenge your current chat partner to a Quiz Battle."""
    if user.state != ChatState.CHATTING or not user.partner_id:
        await query.answer(
            "Join a chat first, then challenge your partner! 💬",
            show_alert=True,
        )
        return
    partner_id = user.partner_id
    try:
        await context.bot.send_message(
            chat_id=partner_id,
            text=(
                "⚔️ **Quiz Battle challenge!**\n\n"
                "Your partner challenged you to a 5-question quiz duel.\n"
                "Whoever answers more correctly wins! 🧠"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "⚔️ Accept Battle", callback_data=f"gqb_acc_{user.user_id}"
                )],
                [InlineKeyboardButton(
                    "❌ Decline", callback_data="games_menu"
                )],
            ]),
        )
    except Exception as e:
        logger.warning(f"Failed to deliver battle challenge: {e}")
        await query.answer("Couldn't reach your partner.", show_alert=True)
        return
    await query.answer("⚔️ Challenge sent!")
    await safe_edit(
        query,
        "⚔️ **Battle challenge sent!**\n\nWaiting for your partner to "
        "accept…",
        parse_mode="Markdown",
        reply_markup=games_menu_keyboard(),
    )


async def handle_battle_accept(update, context, query, user, challenger_id: int) -> None:
    challenger = db.get_user(challenger_id)
    if (
        not challenger
        or user.state != ChatState.CHATTING
        or user.partner_id != challenger_id
    ):
        await query.answer("That battle is no longer available.", show_alert=True)
        return
    if user.banned or challenger.banned:
        await query.answer("Restricted accounts can't battle.", show_alert=True)
        return
    questions = games_mod.battle_questions()
    session = db.create_battle(challenger_id, user.user_id, questions)
    await safe_edit(
        query,
        "⚔️ **Battle started!**\n\n"
        f"{md_escape(display_name(challenger))} goes first. Answer the "
        "questions as they arrive — good luck! 🧠",
        parse_mode="Markdown",
        reply_markup=games_menu_keyboard(),
    )
    await _send_battle_question(context, session)


async def _send_battle_question(context, session: dict) -> None:
    if session.get("done"):
        await _finish_battle(context, session)
        return
    qi = session["qi"]
    if qi >= len(session.get("questions", [])):
        session["done"] = True
        db._write_battles()
        await _finish_battle(context, session)
        return
    q = session["questions"][qi]
    turn = session["turn"]
    rows = [
        [InlineKeyboardButton(
            f"{chr(65 + i)}️⃣ {opt[:40]}", callback_data=f"gqb_ans_{i}"
        )]
        for i, opt in enumerate(q["options"])
    ]
    rows.append([InlineKeyboardButton("❌ Forfeit", callback_data="gqb_quit")])
    await _safe_send(
        context, turn,
        f"⚔️ **Quiz Battle** — Q{qi + 1}/{len(session['questions'])}\n\n"
        f"{md_escape(q['q'])}\n\n"
        f"Your score: {session.get('score', {}).get(str(turn), 0)}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def handle_battle_answer(update, context, query, user, option: int) -> None:
    session = None
    for _key, s in db.game_battles.items():
        if not s.get("done") and user.user_id in (s.get("a"), s.get("b")):
            session = s
            break
    if not session:
        await query.answer("No active battle.", show_alert=True)
        return
    if session.get("turn") != user.user_id:
        await query.answer("It's not your turn!", show_alert=True)
        return
    correct, finished = games_mod.battle_answer(session, user.user_id, option)
    db._write_battles()
    db.add_weekly_points(user.user_id, 1, "game")
    await query.answer("✅ Correct!" if correct else "❌ Wrong answer!")
    if finished:
        await _finish_battle(context, session)
        return
    await _send_battle_question(context, session)


async def _finish_battle(context, session: dict) -> None:
    result = games_mod.battle_result(session)
    a, b = result["a"], result["b"]
    winner = result["winner_id"]
    if winner:
        line_a = "🏆 Winner!" if winner == a else "😅 Better luck next time!"
        line_b = "🏆 Winner!" if winner == b else "😅 Better luck next time!"
    else:
        line_a = line_b = "🤝 It's a draw!"
    await _safe_send(
        context, a,
        f"⚔️ **Battle finished!**\n\n"
        f"You: {result['a_score']} • Opponent: {result['b_score']}\n{line_a}",
        parse_mode="Markdown",
        reply_markup=games_menu_keyboard(),
    )
    await _safe_send(
        context, b,
        f"⚔️ **Battle finished!**\n\n"
        f"You: {result['b_score']} • Opponent: {result['a_score']}\n{line_b}",
        parse_mode="Markdown",
        reply_markup=games_menu_keyboard(),
    )
    db.drop_battle(a, b)


async def handle_battle_quit(update, context, query, user) -> None:
    for _key, s in list(db.game_battles.items()):
        if user.user_id in (s.get("a"), s.get("b")):
            other = s["a"] if s["b"] == user.user_id else s["b"]
            db.drop_battle(s["a"], s["b"])
            await _safe_send(
                context, other,
                "⚔️ Your opponent forfeited the Quiz Battle.",
                reply_markup=games_menu_keyboard(),
            )
            await query.answer("You forfeited the battle.")
            return
    await query.answer("No active battle.", show_alert=True)


# ── Callback routing for every new feature ──────────────────────

async def features_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Handle the new-feature callbacks. Returns True when consumed."""
    query = update.callback_query
    data = query.data or ""
    user = db.get_user(query.from_user.id)
    if not user:
        return False

    if data == "checkin":
        await handle_checkin(update, context, query, user)
        return True
    if data == "checkin_claim":
        await handle_checkin_claim(update, context, query, user)
        return True

    if data == "leaderboard":
        await handle_leaderboard(update, context, query, user)
        return True
    if data == "lb_top":
        await handle_leaderboard(update, context, query, user)
        return True
    if data == "lb_history":
        await handle_lb_history(update, context, query, user)
        return True
    if data == "lb_how":
        await safe_edit(query, LB_HOW_TEXT, parse_mode="Markdown",
                        reply_markup=leaderboard_keyboard())
        return True

    if data == "games_menu":
        in_chat = user.state == ChatState.CHATTING and bool(user.partner_id)
        await safe_edit(
            query,
            "🎮 **Mini-Games**\n\n"
            "Pick a game to play — every game has ⏭ Skip, 🔁 Replay and "
            "❌ Exit. Games also earn you leaderboard points!\n"
            + ("⚔️ In a chat? Challenge your partner to a Quiz Battle below!"
               if in_chat else ""),
            parse_mode="Markdown",
            reply_markup=games_menu_keyboard(battle_challenge=in_chat),
        )
        return True
    if data.startswith("game_"):
        await handle_game_start(update, context, query, user, data[5:])
        return True
    if data in ("gopt_truth", "gopt_dare"):
        await handle_game_option(
            update, context, query, user,
            "truth" if data.endswith("truth") else "dare",
        )
        return True
    if data.startswith("gopt_"):
        await handle_game_option(update, context, query, user, data[5:])
        return True
    if data.startswith("gnum_"):
        await handle_game_number(update, context, query, user, data[5:])
        return True
    if data == "gskip":
        await handle_game_skip(update, context, query, user)
        return True
    if data == "greplay":
        await handle_game_replay(update, context, query, user)
        return True
    if data == "gexit":
        await handle_game_exit(update, context, query, user)
        return True
    if data.startswith("gqb_acc_"):
        await handle_battle_accept(update, context, query, user, int(data[8:]))
        return True
    if data.startswith("gqb_ans_"):
        await handle_battle_answer(update, context, query, user, int(data[8:]))
        return True
    if data == "gqb_quit":
        await handle_battle_quit(update, context, query, user)
        return True
    if data == "gqb_chal":
        await handle_battle_challenge(update, context, query, user)
        return True

    if data == "theme_menu":
        await handle_theme_menu(update, context, query, user)
        return True
    if data.startswith("theme_buy_"):
        await handle_theme_buy(update, context, query, user, data[10:])
        return True
    if data.startswith("theme_eq_"):
        await handle_theme_equip(update, context, query, user, data[9:])
        return True

    if data == "avail_menu":
        await handle_availability_menu(update, context, query, user)
        return True
    if data.startswith("avail_"):
        await handle_availability_set(update, context, query, user, data[6:])
        return True

    if data == "privacy":
        await safe_edit(
            query,
            "🛡️ **Privacy & Safety**\n\nManage how you appear and who can "
            "reach you.",
            parse_mode="Markdown",
            reply_markup=privacy_keyboard(user.daily_reminder),
        )
        return True
    if data == "safety_tips":
        await safe_edit(query, SAFETY_TEXT, parse_mode="Markdown",
                        reply_markup=privacy_keyboard(user.daily_reminder))
        return True

    if data == "discover":
        await safe_edit(
            query,
            "🌍 **Discover People**\n\nHow would you like to find someone?",
            parse_mode="Markdown",
            reply_markup=discover_keyboard(),
        )
        return True

    if data == "edit_bio":
        context.user_data["awaiting_bio"] = True
        await safe_edit(
            query,
            "📝 **Send your bio**\n\nUp to 160 characters — shown on your "
            "profile card. Send /skip or an empty line to clear it.",
            parse_mode="Markdown",
        )
        return True
    if data == "edit_interests":
        context.user_data["awaiting_interests"] = True
        await safe_edit(
            query,
            "🎯 **Send your interests**\n\nComma-separated, e.g. "
            "`music, travel, memes` (max 8). Send /skip to clear.",
            parse_mode="Markdown",
        )
        return True
    if data == "edit_langs":
        context.user_data["awaiting_langs"] = True
        await safe_edit(
            query,
            "🗣 **Send your preferred languages**\n\nComma-separated, e.g. "
            "`English, বাংলা` (max 6). Send /skip to clear.",
            parse_mode="Markdown",
        )
        return True

    return False


# ═══════════════════════════════════════════════════════════════════
#  COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════

async def version_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the running bot version — used to verify a deploy actually landed."""
    await update.message.reply_text(f"talkNhappybot v{BOT_VERSION}")


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
        if target:
            # Your own ID — never end an active chat just for this.
            await update.message.reply_text(
                "🙂 That's your own ID — open it with /profile.",
                reply_markup=main_menu_keyboard(),
            )
            return
        await update.message.reply_text(
            "🔎 This profile no longer exists.",
            reply_markup=main_menu_keyboard(),
        )
        return

    # End any existing chat
    partner_id = db.end_chat(user_id)
    _stamp_chat_end(user_id)
    if partner_id:
        _stamp_chat_end(partner_id)
        await _send_end_block(
            context,
            partner_id,
            notice=CHAT_ENDED_TEXT.format(
                who=format_public_id(existing) if existing else "your partner"
            ),
            offer_choice=False,
        )

    db.remove_from_queue(user_id)
    user = db.register_user(user_id, username, name=first_name)

    # Returning users just get the menu (like the reference bot)
    if not is_new and user.gender and user.country:
        pending = profile_setup_reply(context, user)
        if pending:
            # name/age/city still missing — finish the profile first
            text, markup, mode = pending
            await update.message.reply_text(
                text, parse_mode=mode, reply_markup=markup
            )
            return
        if not await enforce_channel(update, context):
            return
        await update.message.reply_text(
            "🏠 **Main Menu**",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
        await update.message.reply_text(
            "👇 Use the buttons below anytime.",
            reply_markup=_bar(user),
        )
        await send_promo(context, user_id)
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

    # Force-join gate — after registration/referral so nothing is lost
    if not await enforce_channel(update, context):
        return

    await animated_reply(
        update.message,
        bounce_frames(welcome),
        parse_mode="Markdown",
        reply_markup=gender_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await enforce_channel(update, context):
        return
    await animated_reply(
        update.message,
        bounce_frames(HELP_MSG.format(**HELP_KWARGS)),
        parse_mode="Markdown",
    )


async def find_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user:
        await update.message.reply_text("Please /start first to set up your profile.")
        return

    if not await enforce_channel(update, context):
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
        # Never a dead end: leave the current chat and offer the choice.
        await close_chat(context, user_id, leaver_notice="👋 You left the chat.")
        return

    if user.state == ChatState.SEARCHING:
        await update.message.reply_text(
            "⏳ You're already searching for a partner...",
            reply_markup=searching_keyboard(),
        )
        return

    pending = profile_setup_reply(context, user)
    if pending:
        text, markup, mode = pending
        await update.message.reply_text(text, parse_mode=mode, reply_markup=markup)
        return

    await update.message.reply_text(
        SEARCH_CHOICE_TEXT,
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


async def delete_messages_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """"/delet_messages_<slug>" — the 🗑 link handed out when a chat ends.

    Wipes the messages this user sent in the most recent chat, while the
    30-minute window is still open.
    """
    user = db.get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("Please /start first.")
        return
    await _delete_messages_action(update, context, user)


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user:
        await update.message.reply_text("Please /start first.")
        return

    if not await enforce_channel(update, context):
        return

    await ensure_bot_username(context.bot)
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

    if not await enforce_channel(update, context):
        return

    await animated_reply(
        update.message,
        coin_frames(credit_text(user)),
        parse_mode="Markdown",
        reply_markup=credit_keyboard(),
    )


async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user:
        await update.message.reply_text("Please /start first.")
        return

    if not await enforce_channel(update, context):
        return

    link = await get_referral_link(context, user_id)
    await animated_reply(
        update.message,
        bounce_frames(
            f"⚡ **Your personal invite link:**\n`{link}`\n\n"
            f"🎁 You earn **{REFERRAL_REWARD} 🪙** for every friend who joins "
            f"(they get **+{REFERRED_BONUS} 🪙** too).\n\n"
            f"👥 Referrals: **{user.referral_count}**\n"
            f"🪙 Earned from referrals: **{user.referral_earned}**\n"
            f"💰 Balance: **{user.coins} 🪙**"
        ),
        parse_mode="Markdown",
    )


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.get_user(user_id):
        await update.message.reply_text("Please /start first.")
        return

    if not await enforce_channel(update, context):
        return

    text, _ = await process_report(context, user_id)
    await update.message.reply_text(
        text, parse_mode="Markdown", reply_markup=main_menu_keyboard()
    )


async def newchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """💬 Start new chat — leaves any active chat, then searches."""
    user = db.get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("Please /start first.")
        return
    if not await enforce_channel(update, context):
        return
    await start_new_chat_flow(update, context, user)


BROWSE_MENU_TEXT = (
    "🌟 **Who do you want to see?**\n\n"
    "Pick a category below 👇"
)

BROWSE_KIND_TITLES = {
    "myage": "⭐ People My Age",
    "ready": "💕 Ready to Chat",
    "available": "🟢 Ready to Chat",
    "new": "🙋 New Members 🙋",
    "recent": "👀 Recent Chats 👀",
    "popular": "Popular People ❤️",
    "all": "🌍 Everyone",
}


async def browse_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🎉 Browse People — MeChat-style category menu."""
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if not user:
        await update.message.reply_text("Please /start first.")
        return
    if not await enforce_channel(update, context):
        return
    pending = profile_setup_reply(context, user)
    if pending:
        text, markup, mode = pending
        await update.message.reply_text(text, parse_mode=mode, reply_markup=markup)
        return
    await update.message.reply_text(
        BROWSE_MENU_TEXT,
        parse_mode="Markdown",
        reply_markup=browse_menu_keyboard(),
    )


def _load_browse_page(context, user_id: int, kind: str, offset: int = 0):
    """Load one browse page into user_data; returns (users, total)."""
    page, total = db.browse_filtered(user_id, kind, offset, BROWSE_PAGE_SIZE)
    seen = context.user_data.get("browse_ids", []) if offset else []
    merged = (seen + [u.user_id for u in page])[:20]
    context.user_data["browse_ids"] = merged
    context.user_data["browse_offset"] = min(20, offset + len(page))
    context.user_data["browse_total"] = total
    context.user_data["browse_kind"] = kind
    return page, total


async def vip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if not user:
        await update.message.reply_text("Please /start first.")
        return
    if not await enforce_channel(update, context):
        return
    await update.message.reply_text(
        vip_text(user), parse_mode="Markdown", reply_markup=vip_keyboard()
    )


async def checkin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🎁 /checkin — daily login reward."""
    user = db.get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("Please /start first.")
        return
    if not await enforce_channel(update, context):
        return
    claimed, earned, balance = db.claim_daily_checkin(user.user_id)
    if claimed:
        await update.message.reply_text(
            CHECKIN_CLAIMED_TEXT.format(
                earned=earned, balance=balance,
                tomorrow=bot_now().strftime("%d %b"),
            ),
            parse_mode="Markdown",
            reply_markup=checkin_keyboard(claimed_today=True),
        )
    else:
        await update.message.reply_text(
            CHECKIN_ALREADY_TEXT.format(coins=DAILY_CHECKIN_COINS, balance=balance),
            parse_mode="Markdown",
            reply_markup=checkin_keyboard(claimed_today=True),
        )


async def games_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🎮 /games — mini-game menu."""
    user = db.get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("Please /start first.")
        return
    if not await enforce_channel(update, context):
        return
    in_chat = user.state == ChatState.CHATTING and bool(user.partner_id)
    await update.message.reply_text(
        "🎮 **Mini-Games**\n\nPick a game below 👇",
        parse_mode="Markdown",
        reply_markup=games_menu_keyboard(battle_challenge=in_chat),
    )


async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🏆 /leaderboard — weekly leaderboard."""
    user = db.get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("Please /start first.")
        return
    if not await enforce_channel(update, context):
        return
    entries = db.leaderboard_top(10)
    await update.message.reply_text(
        LEADERBOARD_TEXT.format(
            week=current_week_id(),
            top_block=_lb_top_block(entries),
            mine=db.weekly_points_of(user.user_id),
            r1=WEEKLY_REWARD_COINS.get(1, 6),
            r2=WEEKLY_REWARD_COINS.get(2, 4),
            r3=WEEKLY_REWARD_COINS.get(3, 2),
        ),
        parse_mode="Markdown",
        reply_markup=leaderboard_keyboard(),
    )


async def themes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🎨 /themes — customize theme."""
    user = db.get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("Please /start first.")
        return
    if not await enforce_channel(update, context):
        return
    unlocked = set(user.unlocked_themes or []) | {"default"}
    await update.message.reply_text(
        f"🎨 **Customize Theme**\n\n"
        f"💰 Your coins: **{user.coins} 🪙**\n"
        f"🎭 Active: **{get_theme(user.theme).name}**",
        parse_mode="Markdown",
        reply_markup=theme_keyboard(list(THEMES.values()), user.theme, unlocked),
    )


async def avail_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🟢 /avail — set availability status."""
    user = db.get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("Please /start first.")
        return
    if not await enforce_channel(update, context):
        return
    current = getattr(user, "availability", Availability.READY)
    await update.message.reply_text(
        f"🟢 **Your availability:** {_available_label(user)} "
        f"**{current.value.title()}**\n\n"
        f"Pick a new status below (stale statuses auto-expire after "
        f"{AVAILABILITY_TTL // 3600}h).",
        parse_mode="Markdown",
        reply_markup=availability_keyboard(current.value),
    )


async def link_anon_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if not user:
        await update.message.reply_text("Please /start first.")
        return
    if not await enforce_channel(update, context):
        return
    await ensure_bot_username(context.bot)
    link = (
        f"https://t.me/{bot_username()}?start=chat_{public_id_slug(user)}"
        if bot_username()
        else f"/start chat_{public_id_slug(user)}"
    )
    await update.message.reply_text(
        f"👀 **Your anonymous Chat link:**\n`{link}`\n\n"
        f"Anyone who opens it lands straight on your profile card — they can "
        f"like you, send a 💬 Direct Message or a 📨 Chat Request.",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


async def user_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Tapping or pasting a displayed `/user_xxx` ID opens that person's
    profile card — the same flow as the /start chat_<id> deep link.
    """
    user_id = update.effective_user.id
    username = update.effective_user.username
    first_name = getattr(update.effective_user, "first_name", None)
    parts = (update.message.text or "").strip().split()
    if not parts:
        return
    token = parts[0].split("@", 1)[0]  # /user_9d0b@botname → /user_9d0b

    db.register_user(user_id, username, name=first_name)
    if not await enforce_channel(update, context):
        return

    target = db.resolve_id(token)
    if target and target.user_id == user_id:
        await update.message.reply_text(
            "🙂 That's your own ID — open it with /profile.",
            reply_markup=main_menu_keyboard(),
        )
        return
    if not target:
        shown = token.replace("`", "")[:60]
        await update.message.reply_text(
            f"🔎 No account found for ID `{shown}`.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
        return
    db.record_view(user_id, target.user_id)
    context.user_data["list_ids"] = [target.user_id]
    context.user_data["list_title"] = "🔎 Search result"
    context.user_data["list_kind"] = "plain"
    await reply_profile_card(update.message, user_id, target)


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
            f"• `{uid}` (ID `{format_public_id(target) if target else '?'}`) "
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
            reply_markup=settings_keyboard(target.daily_reminder, vip=target.vip),
        )
    except Exception as e:
        logger.warning(f"Failed to notify rejected user {target.user_id}: {e}")


async def upilist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    pending = db.pending_upi_list()
    if not pending:
        await update.message.reply_text("📱 No pending UPI payments.")
        return

    lines = ["📱 **Pending UPI payments**", ""]
    for uid, info in pending:
        target = db.get_user(uid)
        lines.append(
            f"• `{uid}` (ID `{format_public_id(target) if target else '?'}`) "
            f"@{target.username if target and target.username else '-'} "
            f"— **{info['days']} Days — ₹{info['amount']}**"
        )
    lines += [
        "",
        "Approve: `/upiok <id>`   Reject: `/upino <id>`",
        "_(user ID or the 6-digit profile ID)_",
    ]
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    for uid, info in pending:
        try:
            await context.bot.send_photo(
                chat_id=update.effective_user.id,
                photo=info["file_id"],
                caption=(
                    f"📱 UPI proof from {uid} — "
                    f"**{info['days']} Days — ₹{info['amount']}**"
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning(f"Failed to send UPI screenshot for {uid}: {e}")


async def upiok_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /upiok <user_id or 6-digit ID>")
        return
    target = db.resolve_id(context.args[0])
    if not target:
        await update.message.reply_text("No such user.")
        return
    pending = db.pending_upi.get(target.user_id)
    if not pending:
        await update.message.reply_text("Nothing pending for that user.")
        return
    days, amount = pending["days"], pending["amount"]
    user = db.approve_upi_payment(target.user_id)
    if not user:
        await update.message.reply_text("Nothing pending for that user.")
        return
    until = vip_expiry_label(user)
    await update.message.reply_text(
        f"✅ Approved {user.user_id} → VIP {days} Days "
        f"(₹{amount})" + (f" until {until}" if until else "")
    )
    try:
        await context.bot.send_message(
            chat_id=user.user_id,
            text=(
                f"✅ **Payment approved!**\n\n"
                f"👑 **{days} Days VIP** activated"
                + (f" — active until **{until}**." if until else ".")
                + "\n\nEnjoy your VIP benefits!"
            ),
            parse_mode="Markdown",
            reply_markup=vip_keyboard(),
        )
    except Exception as e:
        logger.warning(f"Failed to notify UPI buyer {user.user_id}: {e}")


async def upino_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /upino <user_id or 6-digit ID>")
        return
    target = db.resolve_id(context.args[0])
    if not target:
        await update.message.reply_text("No such user.")
        return
    if not db.reject_upi_payment(target.user_id):
        await update.message.reply_text("Nothing pending for that user.")
        return
    await update.message.reply_text(f"❌ Rejected {target.user_id}")
    try:
        await context.bot.send_message(
            chat_id=target.user_id,
            text=(
                "❌ **Payment not verified**\n\n"
                "The screenshot didn't pass review. You can pay again and "
                "resend from /vip → 📱 Buy VIP via UPI / PhonePe."
            ),
            parse_mode="Markdown",
            reply_markup=vip_keyboard(),
        )
    except Exception as e:
        logger.warning(f"Failed to notify rejected UPI user {target.user_id}: {e}")


# ═══════════════════════════════════════════════════════════════════
#  CALLBACK QUERY HANDLERS (inline buttons)
# ═══════════════════════════════════════════════════════════════════

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    await ensure_bot_username(context.bot)

    user = db.get_user(user_id)
    if not user:
        db.register_user(user_id, query.from_user.username)
        user = db.get_user(user_id)
    db.touch_last_seen(user_id)

    # ── Force-join: "✅ I've Joined" re-check ───────────────
    if data == "joined_check":
        _MEMBER_CACHE.pop(user_id, None)  # always re-verify this tap
        if await is_channel_member(context, user_id):
            await query.answer("✅ Welcome aboard!", show_alert=True)
            await safe_edit(
                query,
                "✅ **Thanks for joining!**\n\nYou can now use the bot — "
                "tap a button below to get started.",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(),
            )
        else:
            await query.answer(
                "⚠️ You haven't joined yet — tap \"📢 Join Channel\" first, "
                "then press ✅ I've Joined.",
                show_alert=True,
            )
        return

    # ── Force-join gate on every other button ──────────────
    if not await enforce_channel(update, context):
        return

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

    # ── New features (check-in, leaderboard, games, themes, …) ──
    if data.startswith((
        "checkin", "lb_", "leaderboard", "games_menu", "game_",
        "gopt_", "gskip", "greplay", "gexit", "gnum_", "gqb_",
        "theme_", "avail_", "privacy", "safety_tips", "discover",
        "edit_bio", "edit_interests", "edit_langs",
    )):
        if await features_handler(update, context):
            return

    # ── Gender selection ────────────────────────────────────
    if data.startswith("gender_"):
        gender = Gender.MALE if data == "gender_male" else Gender.FEMALE
        db.update_gender(user_id, gender)
        await animate_edit(
            query,
            [
                "✅",
                f"✅ Gender set to **{format_gender(gender)}**\n\n"
                "Now select your **country**:",
            ],
            interval=0.35,
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
            if user.vip:
                await animate_edit(
                    query,
                    [
                        "✅",
                        f"✅ Country set to **{country_code}**\n\n"
                        "Who would you like to chat with?",
                    ],
                    interval=0.35,
                    parse_mode="Markdown",
                    reply_markup=preference_keyboard(),
                )
            else:
                # 👑 Partner preference is VIP-only — free users match anyone.
                db.update_preferred_gender(user_id, Gender.ANY)
                context.user_data["setup_flow"] = True
                context.user_data["awaiting_name"] = True
                await animate_edit(
                    query,
                    [
                        "✅",
                        f"✅ Country set to **{country_code}**\n\n"
                        + NAME_ASK_TEXT.strip(),
                    ],
                    interval=0.35,
                    parse_mode="Markdown",
                )

    # ── Gender preference ───────────────────────────────────
    elif data.startswith("pref_"):
        pref_map = {"pref_male": Gender.MALE, "pref_female": Gender.FEMALE, "pref_any": Gender.ANY}
        pref = pref_map.get(data, Gender.ANY)
        if not user.vip:
            # Stale button from an old message — the choice is VIP-only.
            pref = Gender.ANY
        db.update_preferred_gender(user_id, pref)
        label = format_gender(pref) if pref != Gender.ANY else "🌍 Anyone"
        context.user_data["setup_flow"] = True
        context.user_data["awaiting_name"] = True
        await animate_edit(
            query,
            [
                "✅",
                f"✅ You'll be matched with: **{label}**\n\n" + NAME_ASK_TEXT.strip(),
            ],
            interval=0.35,
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

        pending = profile_setup_reply(context, user)
        if pending:
            text, markup, mode = pending
            await safe_edit(query, text, parse_mode=mode, reply_markup=markup)
            return

        if user.state == ChatState.CHATTING:
            # Leave the chat you're in, then offer the choice — no dead end.
            await close_chat(
                context, user_id, leaver_notice="👋 You left the chat.",
                offer_choice=False,
            )

        if user.state == ChatState.SEARCHING:
            await safe_edit(
                query,
                "⏳ You're already searching for a partner...",
                reply_markup=searching_keyboard(),
            )
            return

        await safe_edit(
            query,
            SEARCH_CHOICE_TEXT,
            parse_mode="Markdown",
            reply_markup=search_choice_keyboard(),
        )

    # ── Per-search partner choice ───────────────────────────
    elif data in ("search_random", "search_guy", "search_girl"):
        # 🕺/💃 gender searches are turned off for now — every search is a
        # normal, free Random search (stale Guy/Girl buttons included).
        text, markup, parse_mode = await begin_search(
            context, user_id, Gender.ANY, target=query
        )
        if text:
            await safe_edit(query, text, parse_mode=parse_mode, reply_markup=markup)

    elif data == "my_profile":
        # MeChat-style: own profile always arrives as a photo card
        # (AI avatar is used when no photo was set)
        await ensure_bot_username(context.bot)
        try:
            await typing_pulse(context.bot, user_id, times=1, interval=0.3)
            await context.bot.send_photo(
                chat_id=user_id,
                photo=open_photo(profile_photo_of(user)),
                caption=build_profile_text(user),
                parse_mode="Markdown",
                reply_markup=profile_keyboard(),
            )
            return
        except Exception as e:
            logger.warning(f"Failed to send profile photo card: {e}")
        await typing_pulse(context.bot, user_id, times=1, interval=0.25)
        await safe_edit(
            query, build_profile_text(user), parse_mode="Markdown",
            reply_markup=profile_keyboard(),
        )

    elif data == "blocked_list":
        blocked = db.blocked_of(user_id)
        if not blocked:
            text = (
                "🚫 **No blocked users**\n\n"
                "When you block or report someone, they'll show up here."
            )
        else:
            me = db.get_user(user_id)
            lines = [
                f"• {md_escape(display_name(u, me))} {public_id_link(u)}"
                for u in blocked
            ]
            text = (
                f"🚫 **Blocked Users** ({len(blocked)})\n\n"
                + "\n".join(lines)
                + "\n\nTap a name to Unblock them."
            )
        await safe_edit(
            query, text, parse_mode="Markdown",
            reply_markup=blocked_users_keyboard(blocked),
        )

    elif data.startswith("unblock_"):
        target = db.get_user(int(data[len("unblock_"):]))
        me = db.get_user(user_id)
        if not target or not me or not db.unblock_user(user_id, target.user_id):
            await query.answer("That user isn't in your blocked list.", show_alert=True)
            return
        await query.answer(f"✅ {display_name(target, me)} unblocked")
        blocked = db.blocked_of(user_id)
        await safe_edit(
            query,
            f"🚫 **Blocked Users** ({len(blocked)})\n\nTap a name to Unblock them."
            if blocked
            else "🚫 **No blocked users**",
            parse_mode="Markdown",
            reply_markup=blocked_users_keyboard(blocked),
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
            reply_markup=settings_keyboard(user.daily_reminder, vip=user.vip),
        )

    elif data == "reminder_toggle":
        enabled = not user.daily_reminder
        db.set_daily_reminder(user_id, enabled)
        await query.answer(
            "⏰ Daily reminder ON — one message a day to come back and chat!"
            if enabled
            else "⏰ Daily reminder OFF."
        )
        await safe_edit(
            query,
            (
                "⚙️ **Settings**\n\n"
                "✅ **Daily reminder is ON** — you'll get **1 message a day** "
                "nudging you to use the bot and talk to someone.\n\n"
                "What would you like to change?"
                if enabled
                else "⚙️ **Settings**\n\n"
                "❌ **Daily reminder is OFF**.\n\n"
                "What would you like to change?"
            ),
            parse_mode="Markdown",
            reply_markup=settings_keyboard(enabled, vip=user.vip),
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
        await animate_edit(
            query, coin_frames(credit_text(user)), interval=0.3,
            parse_mode="Markdown", reply_markup=credit_keyboard(),
        )

    # ── VIP screen (Go Back from UPI plans) ─────────────────────
    elif data == "vip":
        await safe_edit(
            query, vip_text(user),
            parse_mode="Markdown", reply_markup=vip_keyboard(),
        )

    # ── UPI / PhonePe VIP purchase ──────────────────────────────
    elif data == "upi_menu":
        context.user_data.pop("upi_plan", None)
        context.user_data["awaiting_upi"] = False
        await safe_edit(
            query,
            "📱 **Buy VIP via UPI / PhonePe**\n\n"
            "Enjoy unlimited chats, priority matching, and gender filters.\n\n"
            "Choose a plan below (prices in INR).",
            parse_mode="Markdown",
            reply_markup=upi_plan_keyboard(),
        )

    elif data.startswith("upi_plan_"):
        try:
            days = int(data.rsplit("_", 1)[1])
            amount = _UPI_PRICES[days]
        except (ValueError, KeyError):
            await safe_edit(
                query, "⚠️ Invalid plan. Please try again.",
                reply_markup=upi_plan_keyboard(),
            )
            return
        context.user_data["upi_plan"] = (days, amount)
        # Arm screenshot capture immediately — the user may send the proof
        # right after the QR without tapping "I Have Paid" first.
        context.user_data["awaiting_upi"] = True
        caption = (
            f"📱 **UPI Payment — {days} Days VIP**\n\n"
            f"Amount: **₹{amount} INR** (exact amount only)\n"
            f"UPI ID: `{UPI_ID}`\n\n"
            f"Pay via the QR or UPI ID, tap **I Have Paid**, then "
            f"send your payment screenshot.\n"
            f"VIP is activated instantly after admin verification."
        )
        try:
            await context.bot.send_photo(
                chat_id=user_id,
                photo=upi_qr_png(amount, days),
                caption=caption,
                parse_mode="Markdown",
                reply_markup=upi_paid_keyboard(),
            )
        except Exception as e:
            logger.error(f"Failed to send UPI QR: {e}", exc_info=True)
            await safe_edit(
                query,
                "⚠️ Could not generate the QR code. Please try again.",
                reply_markup=upi_plan_keyboard(),
            )
            return
        # The tap was already acknowledged at dispatch (button_handler answers
        # every callback once). A second answerCallbackQuery is rejected by
        # Telegram with 400 — keep it best-effort so it can never mask the
        # successful QR send with a false "could not generate" error.
        try:
            await query.answer(f"📱 {days} Days VIP — ₹{amount}")
        except Exception:
            pass
        try:
            await safe_edit(
                query,
                f"⬆️ **QR sent above** — pay **₹{amount} exact**, then tap "
                f"**✅ I Have Paid** and send your screenshot.",
                parse_mode="Markdown",
                reply_markup=upi_paid_keyboard(),
            )
        except Exception as e:
            logger.warning(f"UPI QR sent but message update failed: {e}")

    elif data == "upi_paid":
        plan = context.user_data.get("upi_plan")
        if not plan:
            # Already acknowledged at dispatch — a repeat answer raises, so
            # make it best-effort and never let it skip the plan list below.
            try:
                await query.answer("Pick a plan first.", show_alert=True)
            except Exception:
                pass
            await safe_edit(
                query, "📱 **Buy VIP via UPI / PhonePe**\n\nChoose a plan below.",
                parse_mode="Markdown", reply_markup=upi_plan_keyboard(),
            )
            return
        days, amount = plan
        context.user_data["awaiting_upi"] = True
        await safe_edit(
            query,
            f"📸 **Send your payment screenshot**\n\n"
            f"Plan: **{days} Days VIP — ₹{amount}**\n"
            f"Send a photo of the payment confirmation now.\n"
            f"Send any other message to cancel.",
            parse_mode="Markdown",
            reply_markup=upi_paid_keyboard(),
        )

    elif data == "show_refer":
        link = await get_referral_link(context, user_id)
        await animate_edit(
            query,
            [
                "🎁",
                f"🎁 **Refer Friends (Free Coin)**\n\n"
                f"⚡ Your personal invite link:\n`{link}`\n\n"
            f"Share it with friends — you earn **{REFERRAL_REWARD} 🪙** for each "
            f"friend who joins (they get **+{REFERRED_BONUS} 🪙** too).\n\n"
            f"👥 Referrals: **{user.referral_count}**\n"
            f"🪙 Earned: **{user.referral_earned}**\n"
            f"💰 Balance: **{user.coins} 🪙**",
            ],
            interval=0.3,
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
                name = display_name(liker, user)
                if name == "Stranger":
                    lines.append(f"• {public_id_link(liker)}")
                else:
                    lines.append(f"• {md_escape(name)}")
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
        if not user.vip:
            await query.answer(
                "👑 Choosing who to chat with is a VIP feature.", show_alert=True
            )
            return
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
            reply_markup=settings_keyboard(user.daily_reminder, vip=user.vip),
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
            reply_markup=settings_keyboard(user.daily_reminder, vip=user.vip),
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
            text, markup = await prepare_nearby(context, user_id)
            _remember_list_message(context, query)
            await safe_edit(
                query, text, parse_mode="Markdown", reply_markup=markup
            )

    elif data == "share_location":
        context.user_data["awaiting_location"] = True
        await safe_edit(
            query,
            "📍 **Send your location**\n\n"
            "Any of these works:\n"
            "• 📎 ➡️ 📍 Location (live location works too)\n"
            "• 📎 ➡️ 🏷 place / a pin dropped on the map\n"
            "• paste coordinates like `12.97, 77.59`",
            parse_mode="Markdown",
            reply_markup=share_location_keyboard(),
        )

    elif data == "find_id":
        context.user_data["awaiting_id"] = True
        await safe_edit(
            query,
            "🔎 **Find by ID**\n\n"
            "Type the person's ID: their 6-digit number (see yours in "
            "/profile) or their `/user_xxx` ID — both work.",
            parse_mode="Markdown",
        )

    elif data == "contacts":
        users = db.contacts_of(user_id)
        me = db.get_user(user_id)
        pairs = [(_plain_label(u, me), u) for u in users]
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

        # Profile opened without a list behind it (deep link, /user_xxx,
        # "someone viewed you" toast) — Back returns to the main menu.
        if kind != "browse" and not ids:
            await safe_edit(
                query,
                "🏠 **Main Menu**",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(),
            )
            return

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
                text = _list_text(title, pairs, db.get_user(user_id), kind)
                markup = _list_markup(kind, pairs)
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
            query, _list_text(title, pairs, db.get_user(user_id), kind),
            parse_mode="Markdown",
            reply_markup=_list_markup(kind, pairs),
        )

    elif data.startswith("view_") and data[5:].isdigit():
        target = db.get_user(int(data[5:]))
        if not target:
            await query.answer("That account no longer exists.", show_alert=True)
            return
        context.user_data["profile_back"] = "back_list"
        _remember_list_message(context, query)
        await show_user_card(query, context, user_id, target)
        if db.record_view(user_id, target.user_id):
            await notify_profile_view(context, user_id, target)

    # ── In-chat: flip the match card into the partner's profile ──
    elif data == "pview":
        target = db.get_user(user.partner_id) if user.partner_id else None
        if user.state != ChatState.CHATTING or not target:
            await query.answer("⚠️ No active chat right now.", show_alert=True)
            return
        context.user_data["profile_back"] = "pback"
        await safe_edit(
            query,
            build_user_card(target, user_id),
            parse_mode="Markdown",
            reply_markup=profile_view_keyboard(
                target.user_id,
                user_id in target.liked_by,
                notify=user.notify_on_end,
                back="pback",
            ),
        )

    elif data == "pback":
        stored = _user_data(context, user_id).get("match_card")
        if (
            user.state == ChatState.CHATTING
            and user.partner_id
            and stored
            and stored[0] == user.partner_id
        ):
            context.user_data["profile_back"] = "back_list"
            await safe_edit(
                query, stored[1], parse_mode="Markdown", reply_markup=chat_keyboard(secure=user.secure_chat)
            )
        else:
            await safe_edit(
                query,
                "🏠 **Main Menu**",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(),
            )

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
        dm_ok, dm_reason = db.can_direct_message(user_id, target.user_id)
        if not dm_ok:
            await query.answer(dm_reason, show_alert=True)
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
        if not db.spend_coins(user_id, DIRECT_MESSAGE_COST):
            await query.answer(
                f"🪙 Not enough Coins! A Direct Message costs "
                f"{DIRECT_MESSAGE_COST} 🪙.",
                show_alert=True,
            )
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"🪙 **Not enough Coins!**\n\n"
                    f"Starting a Direct Message costs **{DIRECT_MESSAGE_COST} 🪙**.\n"
                    f"Invite friends (/link) or buy Coins (/credit) to earn more."
                ),
                parse_mode="Markdown",
                reply_markup=credit_keyboard(),
            )
            return
        if user.state == ChatState.SEARCHING:
            db.remove_from_queue(user_id)
        if not db.pair_users(user_id, target.user_id):
            # Race: they got paired while this tap was in flight — the
            # match failed, so the coins must not stay spent.
            db.add_coins(user_id, DIRECT_MESSAGE_COST)
            await query.answer(
                "That chat couldn't start — please try again.", show_alert=True
            )
            return
        balance = db.get_user(user_id).coins
        await safe_edit(
            query,
            f"💬 **Direct chat started! Say hi 👋**\n"
            f"🪙 -{DIRECT_MESSAGE_COST} | Balance: {balance}",
            parse_mode="Markdown",
            reply_markup=chat_keyboard(secure=db.get_user(user_id).secure_chat),
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
                offer_choice=False,
            )
        else:
            await query.answer("🔒 Blocked — you won't be matched again.")

    elif data.startswith("rpt_") or (
        data.startswith("report_")
        and data != "report_partner"
        and data[len("report_"):].isdigit()
    ):
        # "report_<id>" is what 🚩 Report User sends — accept it as well
        # as the short "rpt_<id>" form used by older messages.
        raw_id = (
            data[len("rpt_"):] if data.startswith("rpt_") else data[len("report_"):]
        )
        target = db.get_user(int(raw_id))
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
                offer_choice=False,
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
        if user.notify_on_end:
            db.set_notify_end(user_id, False)
            enabled = False
            toast = "🔕 Chat-end alerts are off."
        elif user.vip:
            db.set_notify_end(user_id, True)
            enabled = True
            toast = "🔔 You'll get a ping when the chat ends — free for VIP 👑"
        elif db.spend_coins(user_id, NOTIFY_COST):
            db.set_notify_end(user_id, True)
            enabled = True
            balance = db.get_user(user_id).coins
            toast = (
                f"🔔 You'll get a ping when the chat ends — "
                f"🪙 -{NOTIFY_COST} | Balance: {balance}"
            )
        else:
            await query.answer(
                f"🪙 Not enough Coins! Switching 🔔 alerts on costs "
                f"{NOTIFY_COST} 🪙 (free for 👑 VIP members).",
                show_alert=True,
            )
            return
        await query.answer(toast)
        await safe_edit(
            query,
            build_user_card(target, user_id),
            parse_mode="Markdown",
            reply_markup=profile_view_keyboard(
                target.user_id, user_id in target.liked_by, notify=enabled,
                back=context.user_data.get("profile_back", "back_list"),
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
                target.user_id, liked, notify=user.notify_on_end,
                back=context.user_data.get("profile_back", "back_list"),
            ),
        )

    # ── Browse People ──────────────────────────────────────
    elif data == "browse_menu":
        pending = profile_setup_reply(context, user)
        if pending:
            text, markup, mode = pending
            await safe_edit(query, text, parse_mode=mode, reply_markup=markup)
            return
        await safe_edit(
            query,
            BROWSE_MENU_TEXT,
            parse_mode="Markdown",
            reply_markup=browse_menu_keyboard(),
        )

    elif data.startswith("brw_"):
        pending = profile_setup_reply(context, user)
        if pending:
            text, markup, mode = pending
            await safe_edit(query, text, parse_mode=mode, reply_markup=markup)
            return
        kind = data[len("brw_"):]
        page, total = await asyncio.to_thread(
            db.browse_filtered, user_id, kind, 0, BROWSE_PAGE_SIZE
        )
        context.user_data["browse_ids"] = [u.user_id for u in page]
        context.user_data["browse_offset"] = len(page)
        context.user_data["browse_total"] = total
        context.user_data["browse_kind"] = kind
        title = BROWSE_KIND_TITLES.get(kind, "🎉 People online")
        context.user_data["list_ids"] = context.user_data["browse_ids"]
        context.user_data["list_title"] = title
        context.user_data["list_kind"] = "browse"
        text, markup = _browse_state(context, user_id)
        _remember_list_message(context, query)
        await animate_edit(
            query,
            ["✨", f"🌟 Loading {title}…", text],
            interval=0.3,
            parse_mode="Markdown",
            reply_markup=markup,
        )
        # The animation swallows edit failures (flood limits, parse errors,
        # restarts mid-animation) and can leave the message stuck on
        # "Loading…". Always re-send the final list to be safe.
        await safe_edit(query, text, parse_mode="Markdown", reply_markup=markup)

    elif data in ("browse_more", "browse_list"):
        if data == "browse_more":
            offset = context.user_data.get("browse_offset", 0)
            kind = context.user_data.get("browse_kind", "all")
            page, total = await asyncio.to_thread(
                db.browse_filtered, user_id, kind, offset, BROWSE_PAGE_SIZE
            )
            if not page:
                await query.answer(
                    "That's everyone for now — check back soon!", show_alert=True
                )
                return
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

    elif data.startswith("view_msg_"):
        # Reveal a stored direct message (content hidden until tapped)
        dm = db.pop_dm(user_id)
        if not dm:
            await query.answer("No unread messages.", show_alert=True)
            return
        sender = db.get_user(dm.get("from_id"))
        await typing_pulse(context.bot, user_id, times=1, interval=0.25)
        await safe_edit(
            query,
            f"📩 **Message from "
            f"{md_escape(display_name(sender, db.get_user(user_id))) if sender else 'someone'}:**\n\n"
            f"{dm.get('text', '')}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "💬 Open their profile", callback_data=f"view_{dm.get('from_id', 0)}"
                )],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="back_menu")],
            ]),
        )

    elif data == "browse_msg":
        if not context.user_data.get("browse_ids"):
            await query.answer("Open Browse People first.", show_alert=True)
            return
        context.user_data["awaiting_broadcast"] = True
        await safe_edit(
            query,
            "📋 **Send Message to List**\n\n"
            f"Type the message you want to send to the people in your current "
            f"list.\n\n"
            f"🪙 Costs **{LIST_MESSAGE_COST} coins per person** in your "
            f"current list — charged when the message is sent.",
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
            f"{gender_emoji(requester.gender)} "
            f"**{md_escape(display_name(requester, db.get_user(user_id)))}** "
            f"• {public_id_link(requester)}",
            parse_mode="Markdown",
            reply_markup=request_keyboard(requester_id),
        )

    elif data.startswith("req_chat_"):
        target = db.get_user(int(data[len("req_chat_"):]))
        if not target:
            await query.answer("That account no longer exists.", show_alert=True)
            return

        req_ok, req_reason = db.can_direct_message(user_id, target.user_id)
        if not req_ok:
            await query.answer(req_reason, show_alert=True)
            # Toasts vanish in seconds — also leave a persistent message so
            # the sender always sees WHY no request went out.
            await context.bot.send_message(
                chat_id=user_id,
                text=f"⛔ {req_reason}",
                reply_markup=profile_view_keyboard(
                    target.user_id, False, notify=user.notify_on_end,
                    back=context.user_data.get("profile_back", "back_list"),
                ),
            )
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
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"⛔ {reason}",
                    reply_markup=profile_view_keyboard(
                        target.user_id, False, notify=user.notify_on_end,
                        back=context.user_data.get("profile_back", "back_list"),
                    ),
                )
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
                target.user_id, False, notify=user.notify_on_end,
                back=context.user_data.get("profile_back", "back_list"),
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

        if not db.pair_users(requester_id, user_id):
            # Race: one side got paired meanwhile — refund, never charge
            # for a match that didn't happen.
            db.add_coins(requester_id, CHAT_REQUEST_COST)
            await query.answer(
                "This request is no longer valid.", show_alert=True
            )
            return
        await safe_edit(
            query, "✅ **Request accepted! Say hi 👋**",
            parse_mode="Markdown", reply_markup=chat_keyboard(secure=me.secure_chat),
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
    elif data == "secure_chat":
        if user.state != ChatState.CHATTING or not user.partner_id:
            await query.answer("⚠️ No active chat right now.", show_alert=True)
            return
        enabled = not user.secure_chat
        partner_id = db.set_secure_chat(user_id, enabled)
        # Keep the match card in place, but re-label its Secure Chat button.
        stored = _user_data(context, user_id).get("match_card")
        card_text = (
            stored[1]
            if stored and stored[0] == user.partner_id
            else (SECURE_ON_SELF if enabled else SECURE_OFF_SELF)
        )
        await safe_edit(
            query, card_text, parse_mode="Markdown",
            reply_markup=chat_keyboard(secure=enabled),
        )
        # Refresh the 📌 bar on BOTH sides — its Secure Chat label flips too.
        await _safe_send(
            context, user_id,
            SECURE_ON_SELF if enabled else SECURE_OFF_SELF,
            parse_mode="Markdown",
            reply_markup=main_reply_keyboard(secure=enabled, in_chat=True),
        )
        if partner_id:
            await _safe_send(
                context, partner_id,
                SECURE_ON_PARTNER if enabled else SECURE_OFF_PARTNER,
                parse_mode="Markdown",
                reply_markup=main_reply_keyboard(secure=enabled, in_chat=True),
            )

    elif data == "end_chat":
        partner_id = db.end_chat(user_id)
        _stamp_chat_end(user_id)
        if partner_id:
            _stamp_chat_end(partner_id)
        await safe_edit(
            query, "👋 You left the chat.", reply_markup=search_choice_keyboard()
        )
        await _send_end_block(
            context, user_id, notice="👋 You left the chat.", offer_choice=False
        )
        if partner_id:
            await _send_end_block(
                context,
                partner_id,
                notice=CHAT_ENDED_TEXT.format(
                    who=format_public_id(user) if user else "your partner"
                ),
                offer_choice=True,
            )
        await _ping_chat_end(context, user_id, partner_id)

    elif data == "report_partner":
        text, _ = await process_report(context, user_id)
        await safe_edit(
            query, text, parse_mode="Markdown", reply_markup=main_menu_keyboard()
        )

    elif data == "next_partner":
        # End current chat, then let the user choose who to search for next
        await close_chat(context, user_id, offer_choice=False)
        await safe_edit(
            query,
            SEARCH_CHOICE_TEXT,
            parse_mode="Markdown",
            reply_markup=search_choice_keyboard(),
        )

    elif data == "cancel_search":
        db.remove_from_queue(user_id)
        await safe_edit(
            query, "❌ Search cancelled.", reply_markup=main_menu_keyboard()
        )

    else:
        # Unknown/expired callback (old message, stale button) — never a
        # silent dead tap: point the user back at the menu.
        logger.debug(f"Unhandled callback data: {data!r}")
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="⌛ That button has expired — here's the menu again.",
                reply_markup=main_menu_keyboard(),
            )
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Could not send stale-button notice: {e}")


# ═══════════════════════════════════════════════════════════════════
#  MESSAGE RELAY (forwards messages between paired users)
# ═══════════════════════════════════════════════════════════════════

_BAR_NO_CHAT = "⚠️ You're not in a chat right now."


async def _apply_secure_chat(context, user, enabled: bool) -> None:
    """Flip 🔒 Secure Chat for both sides and re-send the bar with the
    new label (a reply keyboard only changes when a message carries it)."""
    partner_id = db.set_secure_chat(user.user_id, enabled)
    await _safe_send(
        context, user.user_id,
        SECURE_ON_SELF if enabled else SECURE_OFF_SELF,
        parse_mode="Markdown",
        reply_markup=main_reply_keyboard(secure=enabled, in_chat=True),
    )
    if partner_id:
        await _safe_send(
            context, partner_id,
            SECURE_ON_PARTNER if enabled else SECURE_OFF_PARTNER,
            parse_mode="Markdown",
            reply_markup=main_reply_keyboard(secure=enabled, in_chat=True),
        )


async def _send_contact_profile(update: Update, context, user) -> None:
    """👤 Contact Profile — the partner's full profile card, in the chat."""
    target = db.get_user(user.partner_id) if user.partner_id else None
    if not target:
        await update.message.reply_text(
            _BAR_NO_CHAT, reply_markup=_bar(user)
        )
        return
    await update.message.reply_text(
        build_user_card(target, user.user_id),
        parse_mode="Markdown",
        reply_markup=profile_view_keyboard(
            target.user_id,
            user.user_id in target.liked_by,
            notify=user.notify_on_end,
            back="pback",
        ),
    )


async def _delete_messages_action(update: Update, context, user) -> None:
    """🗑 Delete Messages — wipe what you sent in the last chat.

    Telegram only lets a bot delete its OWN messages, and the copies of
    what you sent live in the partner's chat — so that's the log we go
    after, but only for messages you originally sent.
    """
    bar = _bar(user)
    partner_id = user.partner_id or _chat_log(user.user_id).get("partner")
    if not partner_id:
        await update.message.reply_text(_BAR_NO_CHAT, reply_markup=bar)
        return

    log = _chat_log(partner_id)
    ended_at = log.get("ended_at")
    if ended_at and time.time() - ended_at > CHAT_DELETE_WINDOW:
        await update.message.reply_text(
            "⏰ Too late — messages can only be deleted within 30 minutes "
            "after the chat ends.",
            reply_markup=bar,
        )
        return

    mine = [e for e in log["ids"] if e.get("src") == user.user_id]
    if not mine:
        await update.message.reply_text(
            "🗑 There's nothing to delete here.", reply_markup=bar
        )
        return

    deleted = 0
    for entry in mine:
        try:
            await context.bot.delete_message(
                chat_id=partner_id, message_id=entry["mid"]
            )
            deleted += 1
        except Exception as e:  # noqa: BLE001
            logger.debug(f"could not delete {entry['mid']}: {e}")
    log["ids"] = [e for e in log["ids"] if e.get("src") != user.user_id]
    await update.message.reply_text(
        f"🗑 Deleted {deleted} message{'s' if deleted != 1 else ''}.",
        reply_markup=bar,
    )


async def start_new_chat_flow(update: Update, context, user) -> None:
    """💬 /newchat and 💕 New Anonymous Chat! — never a dead end."""
    if user.state == ChatState.SEARCHING:
        await update.message.reply_text(
            "⏳ You're already searching for a partner...",
            reply_markup=searching_keyboard(),
        )
        return
    if user.state == ChatState.CHATTING and user.partner_id:
        # Leave the old chat — close_chat hands over the 🎲 choose menu.
        await close_chat(context, user.user_id, leaver_notice="👋 You left the chat.")
        return
    pending = profile_setup_reply(context, user)
    if pending:
        text, markup, mode = pending
        await update.message.reply_text(text, parse_mode=mode, reply_markup=markup)
        return
    text, markup, mode = await begin_search(
        context, user.user_id, Gender.ANY, target=update.message
    )
    if text:
        await update.message.reply_text(text, parse_mode=mode, reply_markup=markup)


async def handle_chat_bar(update: Update, context, user) -> bool:
    """Consume a tap on the persistent bar. Returns True when handled.

    Every bar button works in every state — chatting, searching or idle.
    """
    text = (update.message.text or "").strip()
    if not text:
        return False

    bar = lambda: _bar(user)
    in_chat = user.state == ChatState.CHATTING and user.partner_id

    if text in SECURE_LABELS:
        if not in_chat:
            await update.message.reply_text(_BAR_NO_CHAT, reply_markup=bar())
            return True
        await _apply_secure_chat(context, user, not user.secure_chat)
        return True

    if text == CONTACT_PROFILE_LABEL:
        if not in_chat:
            await update.message.reply_text(_BAR_NO_CHAT, reply_markup=bar())
            return True
        await _send_contact_profile(update, context, user)
        return True

    if text == END_CHAT_LABEL:
        if not in_chat:
            await update.message.reply_text(_BAR_NO_CHAT, reply_markup=bar())
            return True
        await close_chat(context, user.user_id, leaver_notice="👋 You left the chat.")
        return True

    if text == DELETE_LABEL:
        await _delete_messages_action(update, context, user)
        return True

    if text == NEW_CHAT_LABEL:
        await start_new_chat_flow(update, context, user)
        return True

    if text == BROWSE_LABEL:
        pending = profile_setup_reply(context, user)
        if pending:
            p_text, p_markup, p_mode = pending
            await update.message.reply_text(p_text, parse_mode=p_mode, reply_markup=p_markup)
            return True
        await update.message.reply_text(
            BROWSE_MENU_TEXT,
            parse_mode="Markdown",
            reply_markup=browse_menu_keyboard(),
        )
        return True

    if text == NEARBY_LABEL:
        uid = user.user_id
        if not db.has_location(uid):
            context.user_data["awaiting_location"] = True
            await update.message.reply_text(
                f"📍 **Nearby People**\n\nShare your location to see people "
                f"within {NEARBY_RADIUS_KM} km of you.",
                parse_mode="Markdown",
                reply_markup=share_location_keyboard(),
            )
        else:
            text, markup = await prepare_nearby(context, uid)
            reply = await update.message.reply_text(
                text, parse_mode="Markdown", reply_markup=markup
            )
            _remember_reply_list(context, reply)
        return True

    return False


_MSG_POINT_BUCKET: dict[int, tuple] = {}  # user_id -> (week, count, awarded)


def _bump_message_points(user_id: int) -> None:
    """+1 leaderboard point per 5 chat messages (daily-capped in the DB)."""
    week = current_week_id()
    week_n, count, awarded = _MSG_POINT_BUCKET.get(user_id, (week, 0, 0))
    if week_n != week:
        count, awarded = 0, 0
    count += 1
    if count - awarded >= 5:
        db.add_weekly_points(user_id, 1, "message")
        awarded = count
    _MSG_POINT_BUCKET[user_id] = (week, count, awarded)
    # keep the map small
    if len(_MSG_POINT_BUCKET) > 4096:
        for k in list(_MSG_POINT_BUCKET)[:1024]:
            _MSG_POINT_BUCKET.pop(k, None)


async def presence_heartbeat(update: Update, context) -> None:
    """Stamp the sender's last-seen on EVERY interaction (group -1 runs
    before the real handlers), so Online/Offline reflects live activity."""
    who = update.effective_user
    if who:
        db.touch_last_seen(who.id)


async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forward any message to the chat partner."""
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user:
        await update.message.reply_text("Please /start first.")
        return

    db.touch_last_seen(user_id)

    if user.banned:
        await update.message.reply_text("🚫 Your account is restricted.")
        return

    # Force-join gate — nothing goes through until the channel is joined
    if not await enforce_channel(update, context):
        return

    # ── UPI payment screenshot (checked FIRST so profile-photo /
    #    verify flows and chat relay can never swallow the proof) ──
    if context.user_data.get("awaiting_upi") or (
        update.message.photo
        and context.user_data.get("upi_plan")
        and not context.user_data.get("awaiting_photo")
        and not context.user_data.get("awaiting_verify")
    ):
        plan = context.user_data.get("upi_plan")
        if update.message.photo and plan:
            context.user_data["awaiting_upi"] = False
            days, amount = context.user_data.pop("upi_plan", (None, None))
            file_id = update.message.photo[-1].file_id
            db.queue_upi_payment(user_id, days, amount, file_id)
            await update.message.reply_text(
                "📱 **Payment screenshot submitted!**\n\n"
                f"Plan: **{days} Days VIP — ₹{amount}**\n"
                "An admin will verify your payment — you'll get a message "
                "when it's approved.",
                parse_mode="Markdown",
                reply_markup=vip_keyboard(),
            )
            if ADMIN_ID is not None:
                uname = f"@{user.username}" if user.username else "-"
                name = user.name or "-"
                caption = (
                    f"📱 UPI payment submitted\n"
                    f"User: {user_id} ({uname}) — {name}\n"
                    f"Plan: {days} Days VIP — ₹{amount}\n\n"
                    f"Approve: /upiok {user_id}\n"
                    f"Reject: /upino {user_id}"
                )
                notified = False
                try:
                    await context.bot.send_photo(
                        chat_id=ADMIN_ID,
                        photo=file_id,
                        caption=caption,
                    )
                    notified = True
                except Exception as e:
                    logger.warning(f"UPI admin photo notify failed: {e}")
                if not notified:
                    # Fallback: plain text so the admin never misses a payment
                    try:
                        await context.bot.send_message(
                            chat_id=ADMIN_ID,
                            text=(
                                f"📱 UPI payment submitted\n"
                                f"User: {user_id} ({uname}) — {name}\n"
                                f"Plan: {days} Days VIP — ₹{amount}\n"
                                f"Screenshot is in the user's chat with the bot.\n\n"
                                f"Approve: /upiok {user_id}\n"
                                f"Reject: /upino {user_id}"
                            ),
                        )
                        notified = True
                    except Exception as e:
                        logger.error(
                            f"UPI admin text notify also failed "
                            f"(ADMIN_ID={ADMIN_ID}): {e}"
                        )
                if notified:
                    logger.info(
                        f"UPI payment from {user_id} queued and admin notified"
                    )
            else:
                logger.warning(
                    "UPI payment queued but ADMIN_ID is not set — "
                    "admin was NOT notified."
                )
            return
        # Armed for a screenshot but sent something else → cancel cleanly.
        context.user_data["awaiting_upi"] = False
        context.user_data.pop("upi_plan", None)
        await update.message.reply_text(
            "❌ Payment cancelled — tap **📱 Buy VIP via UPI**, pick a plan, "
            "then send the screenshot photo.",
            parse_mode="Markdown",
            reply_markup=vip_keyboard(),
        )
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
                reply_markup=settings_keyboard(user.daily_reminder, vip=user.vip),
            )
        return

    # ── 👤 Bio / Interests / Languages editors ──────────────────
    if context.user_data.get("awaiting_bio"):
        context.user_data["awaiting_bio"] = False
        raw = (update.message.text or "").strip()
        if raw.lower() in ("/skip", "/cancel", "skip", "cancel", "/clear"):
            db.set_bio(user_id, None)
            await update.message.reply_text(
                "✅ Bio cleared.",
                reply_markup=settings_keyboard(user.daily_reminder, vip=user.vip),
            )
            return
        db.set_bio(user_id, raw)
        await update.message.reply_text(
            f"✅ **Bio saved:**\n{md_escape((db.get_user(user_id).bio or '')[:160])}",
            parse_mode="Markdown",
            reply_markup=settings_keyboard(user.daily_reminder, vip=user.vip),
        )
        return

    if context.user_data.get("awaiting_interests"):
        context.user_data["awaiting_interests"] = False
        raw = (update.message.text or "").strip()
        if raw.lower() in ("/skip", "/cancel", "skip", "cancel", "/clear"):
            db.set_interests(user_id, [])
            await update.message.reply_text(
                "✅ Interests cleared.",
                reply_markup=settings_keyboard(user.daily_reminder, vip=user.vip),
            )
            return
        items = [p.strip() for p in raw.split(",") if p.strip()]
        db.set_interests(user_id, items)
        saved = ", ".join(db.get_user(user_id).interests) or "—"
        await update.message.reply_text(
            f"✅ **Interests saved:** {md_escape(saved)}",
            parse_mode="Markdown",
            reply_markup=settings_keyboard(user.daily_reminder, vip=user.vip),
        )
        return

    if context.user_data.get("awaiting_langs"):
        context.user_data["awaiting_langs"] = False
        raw = (update.message.text or "").strip()
        if raw.lower() in ("/skip", "/cancel", "skip", "cancel", "/clear"):
            db.set_languages(user_id, [])
            await update.message.reply_text(
                "✅ Languages cleared.",
                reply_markup=settings_keyboard(user.daily_reminder, vip=user.vip),
            )
            return
        items = [p.strip() for p in raw.split(",") if p.strip()]
        db.set_languages(user_id, items)
        saved = ", ".join(db.get_user(user_id).languages) or "—"
        await update.message.reply_text(
            f"✅ **Languages saved:** {md_escape(saved)}",
            parse_mode="Markdown",
            reply_markup=settings_keyboard(user.daily_reminder, vip=user.vip),
        )
        return

    # ── 🔢 Guess the Number: text input for the guess ───────────
    game_state = context.user_data.get("game") or {}
    if (
        game_state.get("kind") == "number"
        and not game_state.get("done")
        and (update.message.text or "").strip().isdigit()
    ):
        guess = int((update.message.text or "").strip())
        feedback = games_mod.number_feedback(game_state, guess)
        game_state["feedback"] = feedback
        context.user_data["game"] = game_state
        if game_state.get("done"):
            db.add_weekly_points(user_id, 1, "game")
        await update.message.reply_text(
            f"🔢 {feedback}\n\n"
            f"{games_mod.score_line(game_state)}\n\n"
            + (
                "🏁 Game over! Tap 🔁 Replay in the game menu to play again."
                if game_state.get("done")
                else "Send another number between "
                f"{game_state.get('low', 1)}–{game_state.get('high', 100)}."
            ),
            reply_markup=game_controls_keyboard(),
        )
        return

    # ── 📍 Location sharing (Nearby search) ─────────────────────
    # A 📍 location, a 🏷 place or pasted coordinates all count — whether we
    # asked for one or the user just dropped a pin while idle.
    _want_loc = bool(context.user_data.get("awaiting_location"))
    _edited_msg = getattr(update, "edited_message", None)
    _msg = update.message if update.message is not None else _edited_msg
    _loc = _message_location(_msg) if _msg is not None else None
    _latlon = (
        (_loc.latitude, _loc.longitude)
        if _loc is not None
        else (
            _coords_from_text(_msg.text or "")
            if _want_loc and _msg is not None
            else None
        )
    )
    if _latlon is not None and _edited_msg is not None and not _want_loc:
        # A live-location tick arrives as an edit — refresh the saved pin
        # quietly instead of re-opening Nearby (or re-relaying) every second.
        db.set_location(user_id, _latlon[0], _latlon[1])
        return
    if _want_loc or (_latlon is not None and user.state != ChatState.CHATTING):
        context.user_data["awaiting_location"] = False
        if _latlon is not None:
            db.set_location(user_id, _latlon[0], _latlon[1])
            body, markup = await prepare_nearby(context, user_id)
            reply = await _msg.reply_text(
                ("✅ Location saved!\n\n" + body) if _want_loc else body,
                parse_mode="Markdown",
                reply_markup=markup,
            )
            _remember_reply_list(context, reply)
            return
        await _msg.reply_text(
            "❌ That wasn't a location — tap 📎 → 📍 Location and send it "
            "(a 🏷 place or pasted coordinates like `12.97, 77.59` work too).",
            parse_mode="Markdown",
            reply_markup=share_location_keyboard(),
        )
        return

    # Handle "Find by ID" text input
    if context.user_data.get("awaiting_id"):
        context.user_data["awaiting_id"] = False
        raw = (update.message.text or "").strip()
        # Accepts 123456, user_xxx or /user_xxx — all resolve the same way.
        target = db.resolve_id(raw)
        if not target:
            shown = (raw or "?").replace("`", "")[:60]
            await update.message.reply_text(
                f"🔎 No account found for ID `{shown}`.",
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
                reply_markup=settings_keyboard(user.daily_reminder, vip=user.vip),
            )
        else:
            await update.message.reply_text(
                "❌ Verification cancelled — pick your gender first, then send "
                "a photo.",
                reply_markup=settings_keyboard(user.daily_reminder, vip=user.vip),
            )
        return

    # Handle country text input
    if context.user_data.get("awaiting_country"):
        country = update.message.text.strip()
        db.update_country(user_id, country)
        context.user_data["awaiting_country"] = False
        if user.vip:
            await update.message.reply_text(
                f"✅ Country set to **{country}**\n\n"
                "Who would you like to chat with?",
                parse_mode="Markdown",
                reply_markup=preference_keyboard(),
            )
        else:
            # 👑 Partner preference is VIP-only — free users match anyone.
            db.update_preferred_gender(user_id, Gender.ANY)
            context.user_data["setup_flow"] = True
            context.user_data["awaiting_name"] = True
            await update.message.reply_text(
                f"✅ Country set to **{country}**\n\n" + NAME_ASK_TEXT.strip(),
                parse_mode="Markdown",
            )
        return

    # Handle age text input (onboarding + Settings)
    if context.user_data.get("awaiting_age"):
        raw = (update.message.text or "").strip()
        if not (raw.isdigit() and 10 <= int(raw) <= 99):
            await update.message.reply_text(
                "⚠️ Please send your age as a number between 10 and 99.",
                reply_markup=_bar(user),
            )
            return
        db.update_age(user_id, int(raw))
        context.user_data["awaiting_age"] = False
        if context.user_data.get("setup_flow"):
            await _next_setup_step(
                update, context, user_id, f"✅ Age set to **{raw}**"
            )
        else:
            await update.message.reply_text(
                f"✅ Age set to **{raw}**",
                parse_mode="Markdown",
                reply_markup=settings_keyboard(user.daily_reminder, vip=user.vip),
            )
        return

    # Handle city text input (onboarding + Settings)
    if context.user_data.get("awaiting_city"):
        city = (update.message.text or "").strip()
        if not city:
            await update.message.reply_text(
                "⚠️ Please send a city name.", reply_markup=_bar(user)
            )
            return
        db.update_city(user_id, city)
        context.user_data["awaiting_city"] = False
        setup_flow = context.user_data.pop("setup_flow", False)
        if setup_flow:
            await _next_setup_step(
                update, context, user_id, f"✅ City set to **{city}**"
            )
        else:
            await update.message.reply_text(
                f"✅ City set to **{city}**",
                parse_mode="Markdown",
                reply_markup=settings_keyboard(user.daily_reminder, vip=user.vip),
            )
        return

    # Handle profile name text input (onboarding + Settings)
    if context.user_data.get("awaiting_name"):
        name = (update.message.text or "").strip()
        if not name:
            await update.message.reply_text(
                "⚠️ Please send a name.", reply_markup=settings_keyboard(user.daily_reminder, vip=user.vip)
            )
            return
        db.update_name(user_id, name)
        context.user_data["awaiting_name"] = False
        if context.user_data.get("setup_flow"):
            await _next_setup_step(
                update, context, user_id, f"✅ Name set to **{md_escape(name)}**"
            )
        else:
            await update.message.reply_text(
                f"✅ Name set to **{md_escape(name)}**",
                parse_mode="Markdown",
                reply_markup=settings_keyboard(user.daily_reminder, vip=user.vip),
            )
        return

    # Handle "📋 Send Message to List"
    if context.user_data.get("awaiting_broadcast"):
        context.user_data["awaiting_broadcast"] = False
        text = (update.message.text or "").strip()
        if not text:
            await update.message.reply_text(
                "❌ Empty message cancelled.", reply_markup=_bar(user)
            )
            return
        recipients = [
            uid
            for uid in context.user_data.get("browse_ids", [])[:20]
            if uid != user_id and db.get_user(uid) and not db.get_user(uid).banned
        ]
        if not recipients:
            await update.message.reply_text(
                "No one to send to right now.", reply_markup=_bar(user)
            )
            return
        total = LIST_MESSAGE_COST * len(recipients)
        if user.coins < total:
            await update.message.reply_text(
                f"🪙 **Not enough Coins!** Sending a message to the list costs "
                f"**{LIST_MESSAGE_COST} 🪙 per person** — "
                f"{len(recipients)} {'person' if len(recipients) == 1 else 'people'} "
                f"= **{total} 🪙**.",
                parse_mode="Markdown",
                reply_markup=credit_keyboard(),
            )
            return
        db.spend_coins(user_id, total)
        sent = 0
        for uid in recipients:
            db.queue_dm(uid, user_id, text)
            try:
                # Privacy-first: content stays hidden until the receiver taps
                await context.bot.send_message(
                    chat_id=uid,
                    text=(
                        "🔔 You have a new #direct message\n\n"
                        "To view the message, click the button below"
                    ),
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(
                            "👀 View Message", callback_data=f"view_msg_{user_id}"
                        )]
                    ]),
                )
                sent += 1
            except Exception as e:
                logger.warning(f"Failed to deliver list message to {uid}: {e}")
        await update.message.reply_text(
            f"✅ Message sent to {sent} {'person' if sent == 1 else 'people'} "
            f"(-{total} 🪙 · {LIST_MESSAGE_COST} 🪙 per person).",
            reply_markup=_bar(user),
        )
        return

    # ── Persistent bottom bar (works in every state) ────────────
    if update.message.text and await handle_chat_bar(update, context, user):
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
    # Secure Chat: block forwarding/saving of the relayed message.
    secure = user.secure_chat

    # 🏆 +1 point per 5 relayed messages (daily-capped inside the DB)
    _bump_message_points(user_id)

    async def _to_partner(kind: str, **kwargs):
        """Send to the partner and remember it for 🗑 Delete Messages."""
        sent = await getattr(context.bot, f"send_{kind}")(
            chat_id=partner_id, protect_content=secure, **kwargs
        )
        _track_chat_msg(partner_id, sent, src=user.user_id)
        return sent

    try:
        # Relay different message types — raw content only, no emoji prefixes
        if msg.text:
            await _to_partner("message", text=msg.text)
        elif msg.photo:
            await _to_partner(
                "photo",
                photo=msg.photo[-1].file_id,
                caption=msg.caption or "",
            )
        elif msg.sticker:
            await _to_partner("sticker", sticker=msg.sticker.file_id)
        elif msg.voice:
            await _to_partner("voice", voice=msg.voice.file_id)
        elif msg.video:
            await _to_partner(
                "video", video=msg.video.file_id, caption=msg.caption or ""
            )
        elif msg.video_note:
            await _to_partner("video_note", video_note=msg.video_note.file_id)
        elif msg.animation:
            await _to_partner(
                "animation",
                animation=msg.animation.file_id,
                caption=msg.caption or "",
            )
        elif msg.document:
            await _to_partner(
                "document",
                document=msg.document.file_id,
                caption=msg.caption or "",
            )
        elif msg.location:
            await _to_partner(
                "location",
                latitude=msg.location.latitude,
                longitude=msg.location.longitude,
            )
        elif getattr(msg, "venue", None):
            await _to_partner(
                "location",
                latitude=msg.venue.location.latitude,
                longitude=msg.venue.location.longitude,
            )
        else:
            await update.message.reply_text("⚠️ This message type is not supported.")
    except Forbidden as e:
        # The partner blocked the bot / deleted their account — wrap up
        # politely instead of spamming a dead chat with failures.
        logger.debug(f"partner {partner_id} unreachable: {e}")
        await close_chat(
            context, user.user_id,
            leaver_notice="⚠️ Your partner is no longer available — "
                          "the chat has ended.",
            offer_choice=True,
        )
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
    db.add_charge(charge_id)

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
            await animated_reply(
                update.message,
                coin_frames(
                    f"✅ **Payment successful!**\n\n"
                    f"🪙 +{coins} Coins\n"
                    f"💰 Balance: **{balance} Coins**"
                    f"{vip_line}"
                ),
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
    def _send_ok(self, with_body: bool = True):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        if with_body:
            self.wfile.write(b"OK")

    def do_GET(self):
        self._send_ok(with_body=True)

    def do_HEAD(self):
        self._send_ok(with_body=False)

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


async def on_startup(application):
    """Start the hourly reminder sweep, then restore/backup the DB."""
    logger.info(f"talkNhappybot v{BOT_VERSION} starting up")
    logger.info(
        f"ADMIN_ID={ADMIN_ID} — UPI/verification admin alerts enabled"
        if ADMIN_ID is not None
        else "ADMIN_ID is NOT SET — UPI/verification admin alerts are DISABLED"
    )
    try:
        me = await application.bot.get_me()
        set_bot_username(me.username)
    except Exception as e:  # noqa: BLE001 — non-fatal, links degrade gracefully
        logger.warning(f"Could not cache bot username at startup: {e}")
    await set_bot_commands(application)
    application.create_task(_reminder_loop(application.bot))
    application.create_task(_weekly_sweep_loop(application.bot))
    application.create_task(_broadcast_loop(application.bot))
    backup_bot = await _get_backup_bot(application.bot)
    await restore_db_from_backup(backup_bot)
    # Re-arm every queued searcher (fresh timeout window, FIFO order kept)
    # and drop broken rows — after a restore the queue may be brand new.
    await asyncio.to_thread(db.recover_searches)
    await _startup_checks(application)
    if _backup_enabled() or _github_enabled():
        await upload_db_backup(backup_bot)
        application.create_task(_backup_loop(backup_bot))
        targets = []
        if _github_enabled():
            targets.append(f"github:{BACKUP_GITHUB_REPO}")
        if _backup_enabled():
            who = "dedicated bot" if backup_bot is not application.bot else "main bot"
            targets.append(f"channel {BACKUP_CHANNEL} via {who}")
        logger.info(
            f"💾 Auto-backup enabled → {' + '.join(targets)} "
            f"every {BACKUP_INTERVAL // 60} min (only when the DB changed)."
        )


async def on_shutdown(application):
    """Take one final snapshot so the next deploy resumes exactly here."""
    try:
        if _backup_enabled() or _github_enabled():
            await upload_db_backup(await _get_backup_bot(application.bot))
    finally:
        if _dedicated_backup_bot is not None:
            try:
                await _dedicated_backup_bot.shutdown()
            except Exception:  # noqa: BLE001 — closing a backup bot must not fail shutdown
                pass
        db.close()


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

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )

    # Presence heartbeat — runs before every other handler
    app.add_handler(MessageHandler(filters.ALL, presence_heartbeat), group=-1)
    app.add_handler(CallbackQueryHandler(presence_heartbeat), group=-1)

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
    app.add_handler(CommandHandler("checkin", checkin_command))
    app.add_handler(CommandHandler("games", games_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard_command))
    app.add_handler(CommandHandler("themes", themes_command))
    app.add_handler(CommandHandler("avail", avail_command))
    app.add_handler(CommandHandler("link", link_command))
    app.add_handler(CommandHandler("link_anon", link_anon_command))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("version", version_command))

    # Admin verification review
    app.add_handler(CommandHandler("verifylist", verifylist_command))
    app.add_handler(CommandHandler("verifyok", verifyok_command))
    app.add_handler(CommandHandler("verifyno", verifyno_command))

    # Admin UPI payment review
    app.add_handler(CommandHandler("upilist", upilist_command))
    app.add_handler(CommandHandler("upiok", upiok_command))
    app.add_handler(CommandHandler("upino", upino_command))

    # Tappable / pasted profile IDs: /user_9d0b (or /user_9d0b@botname)
    app.add_handler(MessageHandler(
        filters.Regex(r"^/user_[0-9a-zA-Z]+"), user_id_command
    ))

    # 🗑 /delet_messages_9d0b — handed out by the chat-end notice
    app.add_handler(MessageHandler(
        filters.Regex(r"^/delet_messages_[0-9a-zA-Z]+"), delete_messages_command
    ))

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
        | filters.LOCATION
        | filters.VENUE,
        relay_message,
    ))

    print("🤖 Bot is running! Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
