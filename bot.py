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
)

load_dotenv()
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")


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

**Coins:**
• Chatting with anyone is **free**
• Searching for a 👩 **Girl** costs **{cost} 🪙 per search**
• Earn Coins by inviting friends with /link
• Buy Coins with Telegram Stars via /credit
"""

PROFILE_TEMPLATE = """
👤 **Your Profile**

🔹 **Gender:** {gender}
🔹 **Country:** {country}
🔹 **Looking for:** {preference}
🔹 **Total chats:** {total_chats}
🔹 **Likes:** ❤️ {likes}
🔹 **Coins:** 🪙 {coins}
🔹 **Referrals:** {referrals}
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
            f"👤 Gender: **{format_gender(p.gender)}**\n\n"
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
        gender=format_gender(user.gender),
        country=user.country or "Not set",
        preference=format_gender(user.preferred_gender)
        if user.preferred_gender != Gender.ANY
        else "🌍 Anyone",
        total_chats=user.total_chats,
        likes=user.likes,
        coins=user.coins,
        referrals=user.referral_count,
        status=format_state(user.state),
    )


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
        HELP_MSG.format(cost=GIRL_SEARCH_COST), parse_mode="Markdown"
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
