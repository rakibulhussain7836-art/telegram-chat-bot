"""
Telegram Random Chat Bot — Main Bot Logic

Commands:
  /start    — Register & show main menu
  /find     — Find a random partner
  /stop     — End current chat
  /profile  — View your profile
  /help     — Show help

Supports: text, photos, stickers, voice, video, documents, GIFs
"""

import os
import logging
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from database import db, Gender, ChatState
from keyboards import (
    gender_keyboard,
    preference_keyboard,
    country_keyboard,
    main_menu_keyboard,
    settings_keyboard,
    chat_keyboard,
    searching_keyboard,
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
/find — Search for a chat partner
/stop — End the current conversation
/profile — View your profile
/help — Show this help message

**During a chat:**
• Send any message — it's forwarded anonymously
• Supports: text, photos, stickers, voice, video, GIFs
• Press ⏭️ **Next** to find a new partner
• Press 🛑 **End** to stop chatting

**Settings:**
You can change your gender, country, and partner preference anytime from the settings menu.
"""

PROFILE_TEMPLATE = """
👤 **Your Profile**

🔹 **Gender:** {gender}
🔹 **Country:** {country}
🔹 **Looking for:** {preference}
🔹 **Total chats:** {total_chats}
🔹 **Status:** {status}
"""


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


# ═══════════════════════════════════════════════════════════════════
#  COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username

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

    await update.message.reply_text(
        WELCOME_MSG,
        parse_mode="Markdown",
        reply_markup=gender_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_MSG, parse_mode="Markdown")


async def find_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user:
        await update.message.reply_text("Please /start first to set up your profile.")
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

    # Add to queue and attempt immediate match
    db.add_to_queue(user_id)
    match_id = db.find_match(user_id)

    if match_id:
        db.pair_users(user_id, match_id)
        await notify_partner_found(context, user_id, match_id)
    else:
        await update.message.reply_text(
            "🔍 **Searching for a partner...**\n\n"
            f"👥 {db.searching_count} people in queue\n"
            "Please wait, you'll be connected soon!",
            parse_mode="Markdown",
            reply_markup=searching_keyboard(),
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

    text = PROFILE_TEMPLATE.format(
        gender=format_gender(user.gender),
        country=user.country or "Not set",
        preference=format_gender(user.preferred_gender) if user.preferred_gender != Gender.ANY else "🌍 Anyone",
        total_chats=user.total_chats,
        status=format_state(user.state),
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())


# ═══════════════════════════════════════════════════════════════════
#  CALLBACK QUERY HANDLERS (inline buttons)
# ═══════════════════════════════════════════════════════════════════

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    user = db.get_user(user_id)
    if not user:
        db.register_user(user_id, query.from_user.username)
        user = db.get_user(user_id)

    # ── Gender selection ────────────────────────────────────
    if data.startswith("gender_"):
        gender = Gender.MALE if data == "gender_male" else Gender.FEMALE
        db.update_gender(user_id, gender)
        await query.edit_message_text(
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
            await query.edit_message_text(
                "🌐 Type your **country name** below:",
                parse_mode="Markdown",
            )
        else:
            db.update_country(user_id, country_code)
            await query.edit_message_text(
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
        await query.edit_message_text(
            f"✅ You'll be matched with: **{label}**\n\n"
            "🎉 You're all set! Use the menu below to find a partner.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )

    # ── Main menu actions ───────────────────────────────────
    elif data == "find_partner":
        if not user.gender or not user.country:
            await query.edit_message_text(
                "⚠️ Complete your profile first.\nUse /start to set up.",
            )
            return

        if user.state == ChatState.CHATTING:
            await query.edit_message_text(
                "You're already in a chat! Use /stop to leave first.",
                reply_markup=chat_keyboard(),
            )
            return

        db.add_to_queue(user_id)
        match_id = db.find_match(user_id)

        if match_id:
            db.pair_users(user_id, match_id)
            await query.edit_message_text("🎉 Partner found! Connecting...")
            await notify_partner_found(context, user_id, match_id)
        else:
            await query.edit_message_text(
                "🔍 **Searching for a partner...**\n\n"
                f"👥 {db.searching_count} people in queue\n"
                "Please wait!",
                parse_mode="Markdown",
                reply_markup=searching_keyboard(),
            )

    elif data == "my_profile":
        text = PROFILE_TEMPLATE.format(
            gender=format_gender(user.gender),
            country=user.country or "Not set",
            preference=format_gender(user.preferred_gender) if user.preferred_gender != Gender.ANY else "🌍 Anyone",
            total_chats=user.total_chats,
            status=format_state(user.state),
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

    elif data == "stats":
        await query.edit_message_text(
            f"📊 **Bot Statistics**\n\n"
            f"👥 Registered users: **{db.online_count}**\n"
            f"🔍 Searching now: **{db.searching_count}**\n"
            f"💬 Active chats: **{db.chatting_count}**",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )

    elif data == "settings":
        await query.edit_message_text(
            "⚙️ **Settings**\n\nWhat would you like to change?",
            parse_mode="Markdown",
            reply_markup=settings_keyboard(),
        )

    elif data == "back_menu":
        await query.edit_message_text(
            "🏠 **Main Menu**",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )

    # ── Settings sub-actions ────────────────────────────────
    elif data == "change_gender":
        await query.edit_message_text(
            "Select your new **gender**:",
            parse_mode="Markdown",
            reply_markup=gender_keyboard(),
        )

    elif data == "change_country":
        await query.edit_message_text(
            "Select your new **country**:",
            parse_mode="Markdown",
            reply_markup=country_keyboard(),
        )

    elif data == "change_pref":
        await query.edit_message_text(
            "Who would you like to chat with?",
            parse_mode="Markdown",
            reply_markup=preference_keyboard(),
        )

    # ── Chat controls ───────────────────────────────────────
    elif data == "end_chat":
        partner_id = db.end_chat(user_id)
        await query.edit_message_text(
            "👋 Chat ended.",
            reply_markup=main_menu_keyboard(),
        )
        if partner_id:
            await context.bot.send_message(
                chat_id=partner_id,
                text="⚠️ Your partner has left the chat.",
                reply_markup=main_menu_keyboard(),
            )

    elif data == "next_partner":
        # End current chat and immediately search for a new one
        partner_id = db.end_chat(user_id)
        if partner_id:
            await context.bot.send_message(
                chat_id=partner_id,
                text="⚠️ Your partner has left the chat.",
                reply_markup=main_menu_keyboard(),
            )

        db.add_to_queue(user_id)
        match_id = db.find_match(user_id)

        if match_id:
            db.pair_users(user_id, match_id)
            await query.edit_message_text("🎉 New partner found! Connecting...")
            await notify_partner_found(context, user_id, match_id)
        else:
            await query.edit_message_text(
                "🔍 **Searching for a new partner...**",
                parse_mode="Markdown",
                reply_markup=searching_keyboard(),
            )

    elif data == "cancel_search":
        db.remove_from_queue(user_id)
        await query.edit_message_text(
            "❌ Search cancelled.",
            reply_markup=main_menu_keyboard(),
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

    # Start health check server in background thread for Koyeb / cloud platforms
    threading.Thread(target=start_health_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("find", find_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("profile", profile_command))

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
