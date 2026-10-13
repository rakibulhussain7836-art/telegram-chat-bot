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

Coins: chatting with anyone is free, searching for a Guy or a Girl costs
2 coins, a chat request costs 2 coins. Every new user starts with 10 coins.
Supports: text, photos, stickers, voice, video, documents, GIFs
"""

import os
import sys
import asyncio
import base64
import logging
import sqlite3
import time
from datetime import datetime
from dotenv import load_dotenv

from telegram import (
    Update,
    LabeledPrice,
    BotCommand,
    Bot,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
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
    GUY_SEARCH_COST,
    CHAT_REQUEST_COST,
    DIRECT_MESSAGE_COST,
    NOTIFY_COST,
    CHAT_REQUEST_TTL,
    NEARBY_RADIUS_KM,
    BROWSE_PAGE_SIZE,
    DAILY_REWARD_COINS,
    REMINDER_HOUR_START,
    REMINDER_HOUR_END,
    format_public_id,
    public_id_slug,
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
    browse_menu_keyboard,
    blocked_users_keyboard,
    promo_keyboard,
    swipe_keyboard,
    vip_keyboard,
    verify_keyboard,
    force_join_keyboard,
    NEW_CHAT_LABEL,
    BROWSE_LABEL,
    NEARBY_LABEL,
)
from animations import (
    ANIMATIONS_ENABLED,
    animate_edit,
    animate_search,
    animate_photo_card,
    animate_message_caption,
    animated_reply,
    typing_pulse,
    celebration_pulse,
    match_photo_frames,
    reveal_frames,
    bounce_frames,
    coin_frames,
    heart_frames,
    emoji_cycle_frames,
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
• Chatting with anyone is **free**
• Searching for a 🕺 **Guy** or a 👩 **Girl** costs **{cost} 🪙 per search**
  (🎲 Random search is free)
• 👑 **VIP** members search for free
• Earn Coins by inviting friends with /link
• Buy Coins with Telegram Stars via /credit
"""

HELP_KWARGS = dict(
    cost=GIRL_SEARCH_COST,
    request_cost=CHAT_REQUEST_COST,
    dm_cost=DIRECT_MESSAGE_COST,
    notify_cost=NOTIFY_COST,
    free=STARTING_COINS,
)

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
🕺 **Chat With Guy ({cost} 🪙 per search)**
💃 **Chat With Girl ({cost} 🪙 per search)**

💡 Talking to anyone is free — only starting a Guy or Girl search costs
{cost} 🪙. 👑 VIP members search for free.
"""

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
🔍 **Searching for a partner…**

🔎 Matching you with a partner…
{count} 👥 people searching right now
⏳ Hang tight — you'll be connected as soon as a match is found!
"""

PROMO_TEXT = (
    "Want to start an anonymous chat? 😎\n\n"
    "Tap 🎲 **Start Random Chat** and start chatting now.\n"
    f"🎁 Girls receive **{DAILY_REWARD_COINS} free coin** per match! 👇"
)


async def send_promo(context, chat_id: int) -> None:
    """MeChat-style pinned promo: nudges the user into a random chat."""
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=PROMO_TEXT,
            parse_mode="Markdown",
            reply_markup=promo_keyboard(None),
        )
    except Exception as e:  # noqa: BLE001
        logger.debug(f"promo skipped for {chat_id}: {e}")


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
    date = today or time.strftime("%Y-%m-%d")
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
        f"💡 *Chatting with anyone is free — a 🕺 Guy or 👩 Girl search costs "
        f"{GIRL_SEARCH_COST} 🪙 each, a 📨 Chat Request {CHAT_REQUEST_COST} 🪙 "
        f"and a 📨 Direct Message from a profile {DIRECT_MESSAGE_COST} 🪙.*\n"
        f"🎁 New accounts start with **{STARTING_COINS} free Coins**."
    )


VIP_PLAN = (6200, 740)  # (coins, stars) — the VIP pack sold via /vip


def vip_text(user) -> str:
    status = "👑 You're a VIP already — thank you!" if user.vip else \
        "🔥 **Upgrade to VIP**"
    return (
        f"{status}\n\n"
        f"👑 **VIP benefits**\n"
        f"• 👩 Girl searches are **free** — and so are 🕺 Guy searches "
        f"(everyone else pays {GIRL_SEARCH_COST} 🪙 each)\n"
        f"• 🔔 Chat-end alerts are **free** (everyone else pays "
        f"{NOTIFY_COST} 🪙 to switch them on)\n"
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
        done_line, parse_mode="Markdown", reply_markup=main_reply_keyboard()
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


async def is_channel_member(context, user_id: int) -> bool:
    """True when the user follows the forced channel (or no channel is set)."""
    if not force_join_required():
        return True
    try:
        member = await context.bot.get_chat_member(FORCE_CHANNEL, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:  # noqa: BLE001 — fail open, never brick the bot
        logger.warning(f"Force-join check failed for {user_id}: {e}")
        return True


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
    """
    user = db.get_user(user_id)
    partner = db.get_user(partner_id)

    for u, p in [(user, partner), (partner, user)]:
        # MeChat-style free coin for starting a chat
        reward = db.award_match_reward(u.user_id)
        reward_line = (
            f"\n🎁 **+{reward} 🪙 free coin** for starting a chat!"
            if reward
            else ""
        )
        partner_info = (
            f"🎉 **Partner found!**\n\n"
            f"{gender_emoji(p.gender)} **{md_escape(display_name(p, u))}**"
            f"{f', {p.age}' if p.age else ''}\n"
            f"📍 {p.city or p.country or 'Unknown'}\n"
            f"👁 {format_online(p)}\n"
            f"🪩 {verified_label(p)}\n"
            + ("👑 VIP member\n" if p.vip else "")
            + f"🆔 `{format_public_id(p)}`\n\n"
            f"Say hi! Type your message below.\n"
            f"Use ⏭ Next Partner to skip.{reward_line}"
        )
        # Short "typing…" beat + match reveal on the photo card itself
        if ANIMATIONS_ENABLED:
            await typing_pulse(context.bot, u.user_id, times=2, interval=0.4)
        delivered = await animate_photo_card(
            context.bot,
            u.user_id,
            open_photo(profile_photo_of(p)),
            match_photo_frames(partner_info),
            reply_markup=chat_keyboard(),
            parse_mode="Markdown",
            interval=0.5,
        )
        if delivered:
            continue
        # No photo available — the match must still be delivered as text.
        try:
            await context.bot.send_message(
                chat_id=u.user_id,
                text=partner_info,
                parse_mode="Markdown",
                reply_markup=chat_keyboard(),
            )
        except Exception as e:
            logger.warning(f"Failed to send match card to {u.user_id}: {e}")


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
    me = await context.bot.get_me()
    return f"https://t.me/{me.username}?start={user_id}"


def build_profile_text(user) -> str:
    return PROFILE_TEMPLATE.format(
        badge="👑" if user.vip else gender_emoji(user.gender),
        name=md_escape(display_name(user, user)),
        age=user.age if user.age else "—",
        city=user.city or (user.country or "—"),
        online=format_online(user),
        public_id=format_public_id(user),
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
    """Profile card in the reference bot's bullet style."""
    viewer = db.get_user(viewer_id)
    place_parts = [p for p in (target.country, target.city) if p]
    place = " (".join([place_parts[0], place_parts[1] + ")"]) if len(place_parts) > 1 else (place_parts[0] if place_parts else "Not set")
    lines = [
        f"{gender_emoji(target.gender)} **{md_escape(display_name(target, viewer))}**",
        f"• Age: {target.age if target.age else '—'}",
        f"• City: {place}",
        f"• Number of likes: {target.likes}",
        "",
        f"Currently {format_online(target)}",
        f"ID: `{format_public_id(target)}`",
        "",
    ]
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


async def show_user_card(query, context, viewer_id: int, target) -> None:
    """
    Open someone's profile as ONE photo card — picture, info and buttons
    in a single message (never a photo with the details trailing below it).
    A continuous emoji cycle plays over the card when it arrives.
    Users without a photo get their AI avatar — everyone has a photo card.
    """
    liked = viewer_id in target.liked_by
    notify = db.get_user(viewer_id).notify_on_end
    markup = profile_view_keyboard(target.user_id, liked, notify)
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


def _nearby_pairs(viewer_id: int) -> list:
    pairs = []
    viewer = db.get_user(viewer_id)
    for target, dist in db.nearby_users(viewer_id):
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
            f"ID: `{format_public_id(target)}`"
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


def _list_text(title: str, pairs) -> str:
    if not pairs:
        return f"{title}\n\nNo one here right now."
    return f"{title}\n\n👥 {len(pairs)} found — tap one to open their profile:"


def _browse_entry(target, viewer=None) -> str:
    """One 🎉 Browse People entry, formatted like the reference bot."""
    place = ", ".join(p for p in (target.country, target.city) if p) or "Not set"
    return (
        f"{gender_emoji(target.gender)} {_list_badges(target)}"
        f"**{md_escape(display_name(target, viewer))}**"
        f"{f', {target.age}' if target.age else ''} • `{public_id_slug(target)}`\n"
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

    if user.state == ChatState.CHATTING:
        return "You're already in a chat! Use /stop to leave first.", chat_keyboard(), None

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

    if match_id:
        db.pair_users(user_id, match_id)
        await notify_partner_found(context, user_id, match_id)
        return "🎉 Partner found! Connecting..." + _charge_line(), None, None

    # Continuous matching animation — cycles until a match lands.
    if target is not None and ANIMATIONS_ENABLED:
        def _check():
            found = db.find_match(user_id)
            if found:
                db.pair_users(user_id, found)
            return found

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
            final_text = "❌ Search cancelled." + _charge_line()
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
            reply_markup=main_reply_keyboard(),
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

    pending = profile_setup_reply(context, user)
    if pending:
        text, markup, mode = pending
        await update.message.reply_text(text, parse_mode=mode, reply_markup=markup)
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

    if not await enforce_channel(update, context):
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
    """💬 Start new chat — jumps straight into a random search."""
    user_id = update.effective_user.id
    if not db.get_user(user_id):
        await update.message.reply_text("Please /start first.")
        return
    if not await enforce_channel(update, context):
        return
    text, markup, mode = await begin_search(
        context, user_id, Gender.ANY, target=update.message
    )
    if text:
        await update.message.reply_text(text, parse_mode=mode, reply_markup=markup)


BROWSE_MENU_TEXT = (
    "🌟 **Who do you want to see?**\n\n"
    "Pick a category below 👇"
)

BROWSE_KIND_TITLES = {
    "myage": "⭐ People My Age",
    "ready": "💕 Ready to Chat",
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


async def link_anon_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if not user:
        await update.message.reply_text("Please /start first.")
        return
    if not await enforce_channel(update, context):
        return
    me = await context.bot.get_me()
    link = f"https://t.me/{me.username}?start=chat_{public_id_slug(user)}"
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
            reply_markup=settings_keyboard(target.daily_reminder),
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

    # ── Force-join: "✅ I've Joined" re-check ───────────────
    if data == "joined_check":
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

    # ── Gender preference ───────────────────────────────────
    elif data.startswith("pref_"):
        pref_map = {"pref_male": Gender.MALE, "pref_female": Gender.FEMALE, "pref_any": Gender.ANY}
        pref = pref_map.get(data, Gender.ANY)
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
        text, markup, parse_mode = await begin_search(
            context, user_id, pref_map[data], target=query
        )
        if text:
            await safe_edit(query, text, parse_mode=parse_mode, reply_markup=markup)

    elif data == "my_profile":
        # MeChat-style: own profile always arrives as a photo card
        # (AI avatar is used when no photo was set)
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
                f"• {md_escape(display_name(u, me))} `{format_public_id(u)}`"
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
            reply_markup=settings_keyboard(user.daily_reminder),
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
            reply_markup=settings_keyboard(enabled),
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
                    name = public_id_slug(liker)
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
            reply_markup=settings_keyboard(user.daily_reminder),
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
            reply_markup=settings_keyboard(user.daily_reminder),
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
            pairs = await asyncio.to_thread(_nearby_pairs, user_id)
            await send_nearby_cards(context, user_id, pairs)
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
        db.pair_users(user_id, target.user_id)
        balance = db.get_user(user_id).coins
        await safe_edit(
            query,
            f"💬 **Direct chat started! Say hi 👋**\n"
            f"🪙 -{DIRECT_MESSAGE_COST} | Balance: {balance}",
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
            f"{gender_emoji(requester.gender)} "
            f"**{md_escape(display_name(requester, db.get_user(user_id)))}** "
            f"• `{format_public_id(requester)}`",
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

    # Force-join gate — nothing goes through until the channel is joined
    if not await enforce_channel(update, context):
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
                reply_markup=settings_keyboard(user.daily_reminder),
            )
        return

    # Handle location sharing (Nearby search)
    if context.user_data.get("awaiting_location"):
        context.user_data["awaiting_location"] = False
        location = update.message.location
        if location:
            db.set_location(user_id, location.latitude, location.longitude)
            pairs = await asyncio.to_thread(_nearby_pairs, user_id)
            await send_nearby_cards(context, user_id, pairs)
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
                reply_markup=settings_keyboard(user.daily_reminder),
            )
        else:
            await update.message.reply_text(
                "❌ Verification cancelled — pick your gender first, then send "
                "a photo.",
                reply_markup=settings_keyboard(user.daily_reminder),
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
            await _next_setup_step(
                update, context, user_id, f"✅ Age set to **{raw}**"
            )
        else:
            await update.message.reply_text(
                f"✅ Age set to **{raw}**",
                parse_mode="Markdown",
                reply_markup=settings_keyboard(user.daily_reminder),
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
            await _next_setup_step(
                update, context, user_id, f"✅ City set to **{city}**"
            )
        else:
            await update.message.reply_text(
                f"✅ City set to **{city}**",
                parse_mode="Markdown",
                reply_markup=settings_keyboard(user.daily_reminder),
            )
        return

    # Handle profile name text input (onboarding + Settings)
    if context.user_data.get("awaiting_name"):
        name = (update.message.text or "").strip()
        if not name:
            await update.message.reply_text(
                "⚠️ Please send a name.", reply_markup=settings_keyboard(user.daily_reminder)
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
                reply_markup=settings_keyboard(user.daily_reminder),
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
            db.queue_dm(uid, user_id, text)
            try:
                # Privacy-first: content stays hidden until the receiver taps
                await context.bot.send_message(
                    chat_id=uid,
                    text=(
                        f"🔔 You have a new #direct message\n\n"
                        f"To view the message, click the button below"
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
            f"✅ Message sent to {sent} {'person' if sent == 1 else 'people'}.",
            reply_markup=main_reply_keyboard(),
        )
        return

    # ── Persistent bottom bar buttons ───────────────────────
    if user.state != ChatState.CHATTING and update.message.text:
        text = update.message.text.strip()
        if text == NEW_CHAT_LABEL:
            reply, markup, mode = await begin_search(
                context, user_id, Gender.ANY, target=update.message
            )
            if reply:
                await update.message.reply_text(reply, parse_mode=mode, reply_markup=markup)
            return
        if text == BROWSE_LABEL:
            pending = profile_setup_reply(context, user)
            if pending:
                p_text, p_markup, p_mode = pending
                await update.message.reply_text(
                    p_text, parse_mode=p_mode, reply_markup=p_markup
                )
                return
            await update.message.reply_text(
                BROWSE_MENU_TEXT,
                parse_mode="Markdown",
                reply_markup=browse_menu_keyboard(),
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
                pairs = await asyncio.to_thread(_nearby_pairs, user_id)
                await send_nearby_cards(context, user_id, pairs)
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
        # Relay different message types — raw content only, no emoji prefixes
        if msg.text:
            await context.bot.send_message(chat_id=partner_id, text=msg.text)
        elif msg.photo:
            await context.bot.send_photo(
                chat_id=partner_id,
                photo=msg.photo[-1].file_id,
                caption=msg.caption or "",
            )
        elif msg.sticker:
            await context.bot.send_sticker(chat_id=partner_id, sticker=msg.sticker.file_id)
        elif msg.voice:
            await context.bot.send_voice(chat_id=partner_id, voice=msg.voice.file_id)
        elif msg.video:
            await context.bot.send_video(
                chat_id=partner_id,
                video=msg.video.file_id,
                caption=msg.caption or "",
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
                caption=msg.caption or "",
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
    await set_bot_commands(application)
    application.create_task(_reminder_loop(application.bot))
    backup_bot = await _get_backup_bot(application.bot)
    await restore_db_from_backup(backup_bot)
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
