"""
Telegram Random Chat Bot — Keyboard Layouts

All inline keyboard builders live here for clean separation.
"""

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from database import (
    CHAT_REQUEST_COST,
    DIRECT_MESSAGE_COST,
)


# ── Gender selection ─────────────────────────────────────────────

def gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👨 Male", callback_data="gender_male"),
            InlineKeyboardButton("👩 Female", callback_data="gender_female"),
        ]
    ])


# ── Gender preference (who to match with) ───────────────────────

def preference_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👨 Males", callback_data="pref_male"),
            InlineKeyboardButton("👩 Females", callback_data="pref_female"),
        ],
        [
            InlineKeyboardButton("🌍 Anyone", callback_data="pref_any"),
        ]
    ])


# ── Country selection (top countries + "Other") ─────────────────

POPULAR_COUNTRIES = [
    ("🇺🇸 USA", "USA"),
    ("🇬🇧 UK", "UK"),
    ("🇮🇳 India", "India"),
    ("🇧🇩 Bangladesh", "Bangladesh"),
    ("🇵🇰 Pakistan", "Pakistan"),
    ("🇧🇷 Brazil", "Brazil"),
    ("🇷🇺 Russia", "Russia"),
    ("🇩🇪 Germany", "Germany"),
    ("🇫🇷 France", "France"),
    ("🇹🇷 Turkey", "Turkey"),
    ("🇮🇩 Indonesia", "Indonesia"),
    ("🇳🇬 Nigeria", "Nigeria"),
    ("🇪🇬 Egypt", "Egypt"),
    ("🇵🇭 Philippines", "Philippines"),
    ("🇲🇽 Mexico", "Mexico"),
]


def country_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(POPULAR_COUNTRIES), 3):
        chunk = POPULAR_COUNTRIES[i : i + 3]
        rows.append([
            InlineKeyboardButton(label, callback_data=f"country_{code}")
            for label, code in chunk
        ])
    rows.append([InlineKeyboardButton("🌐 Other (type your country)", callback_data="country_other")])
    return InlineKeyboardMarkup(rows)


# ── Main menu ────────────────────────────────────────────────────

def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Organised 9-door main menu (feature 6).

    💬 Start Chatting · 🌍 Discover People · 🎮 Play Games ·
    🎁 Daily Check-in · 💰 My Coins · 🏆 Weekly Leaderboard ·
    🎨 Customize Theme · 👤 My Profile · 🛡️ Privacy & Safety
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Start Chatting", callback_data="find_partner")],
        [InlineKeyboardButton("🌍 Discover People", callback_data="discover")],
        [InlineKeyboardButton("🎮 Play Games", callback_data="games_menu")],
        [
            InlineKeyboardButton("🎁 Daily Check-in", callback_data="checkin"),
            InlineKeyboardButton("💰 My Coins", callback_data="credit_menu"),
        ],
        [InlineKeyboardButton("🏆 Weekly Leaderboard", callback_data="leaderboard")],
        [InlineKeyboardButton("🎨 Customize Theme", callback_data="theme_menu")],
        [
            InlineKeyboardButton("👤 My Profile", callback_data="my_profile"),
            InlineKeyboardButton("🛡️ Privacy & Safety", callback_data="privacy"),
        ],
    ])


# ── 🌍 Discover People ───────────────────────────────────────────

def discover_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎉 Browse People", callback_data="browse_menu")],
        [InlineKeyboardButton("🟢 Ready to Chat", callback_data="brw_available")],
        [InlineKeyboardButton("🧭 Nearby People", callback_data="nearby")],
        [InlineKeyboardButton("🔎 Find by ID", callback_data="find_id")],
        [InlineKeyboardButton("📇 My Contacts", callback_data="contacts")],
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_menu")],
    ])


# ── 🛡️ Privacy & Safety ─────────────────────────────────────────

def privacy_keyboard(reminder_on: bool = False) -> InlineKeyboardMarkup:
    reminder_label = (
        "⏰ Daily Reminder: ON ✅" if reminder_on else "⏰ Daily Reminder: OFF"
    )
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 My Availability", callback_data="avail_menu")],
        [InlineKeyboardButton("🚫 Blocked Users", callback_data="blocked_list")],
        [InlineKeyboardButton("⚙️ Advanced Settings", callback_data="settings")],
        [InlineKeyboardButton(reminder_label, callback_data="reminder_toggle")],
        [InlineKeyboardButton("🪩 Get Verified", callback_data="verify_start")],
        [InlineKeyboardButton("📖 Safety Tips", callback_data="safety_tips")],
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_menu")],
    ])


# ── 🟢 Availability status ───────────────────────────────────────

def availability_keyboard(current: str = "ready") -> InlineKeyboardMarkup:
    def mark(label: str, value: str) -> str:
        return f"{label} ✅" if current == value else label
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(mark("🟢 Ready to Chat", "ready"), callback_data="avail_ready")],
        [InlineKeyboardButton(mark("🟡 Busy", "busy"), callback_data="avail_busy")],
        [InlineKeyboardButton(mark("⚫ Invisible", "invisible"), callback_data="avail_invisible")],
        [InlineKeyboardButton("⬅️ Back", callback_data="privacy")],
    ])


# ── 🎮 Mini-games ────────────────────────────────────────────────

def games_menu_keyboard(*, battle_challenge: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("💗 Would You Rather", callback_data="game_wyr")],
        [InlineKeyboardButton("🎭 Truth or Dare", callback_data="game_tod")],
        [InlineKeyboardButton("🧠 Quiz Battle", callback_data="game_quiz")],
        [InlineKeyboardButton("😂 Emoji Guess", callback_data="game_emoji")],
        [InlineKeyboardButton("⚡ Rapid-Fire Questions", callback_data="game_rapid")],
        [InlineKeyboardButton("🔢 Guess the Number", callback_data="game_num")],
        [InlineKeyboardButton("💞 Friendship Quiz", callback_data="game_friend")],
    ]
    if battle_challenge:
        rows.append([InlineKeyboardButton(
            "⚔️ Challenge Partner", callback_data="gqb_chal"
        )])
    rows.append([InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_menu")])
    return InlineKeyboardMarkup(rows)


def game_controls_keyboard(extra_rows=()) -> InlineKeyboardMarkup:
    """Skip / Replay / Exit strip attached to every game card."""
    rows = [
        [
            InlineKeyboardButton("⏭ Skip", callback_data="gskip"),
            InlineKeyboardButton("🔁 Replay", callback_data="greplay"),
            InlineKeyboardButton("❌ Exit", callback_data="gexit"),
        ]
    ]
    rows.extend(extra_rows)
    rows.append([InlineKeyboardButton("🎮 Game Menu", callback_data="games_menu")])
    return InlineKeyboardMarkup(rows)


# ── 🎁 Daily check-in ────────────────────────────────────────────

def checkin_keyboard(claimed_today: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if not claimed_today:
        rows.append([InlineKeyboardButton("🎁 Claim +1 🪙", callback_data="checkin_claim")])
    rows.append([InlineKeyboardButton("💰 My Coins", callback_data="credit_menu")])
    rows.append([InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_menu")])
    return InlineKeyboardMarkup(rows)


# ── 🏆 Weekly leaderboard ────────────────────────────────────────

def leaderboard_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏆 Top 10 This Week", callback_data="lb_top")],
        [InlineKeyboardButton("📜 Previous Weeks", callback_data="lb_history")],
        [InlineKeyboardButton("❓ How points work", callback_data="lb_how")],
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_menu")],
    ])


# ── 🎨 Themes ────────────────────────────────────────────────────

def theme_keyboard(themes, active_theme: str, unlocked: set) -> InlineKeyboardMarkup:
    """List of themes — equip owned ones, buy the rest with coins."""
    rows = []
    for theme in themes:
        if theme.id in unlocked:
            label = f"{theme.emoji} {theme.name}" + (
                " ✅" if theme.id == active_theme else ""
            )
            data = f"theme_eq_{theme.id}"
        else:
            label = f"{theme.emoji} {theme.name} — {theme.cost} 🪙"
            data = f"theme_buy_{theme.id}"
        rows.append([InlineKeyboardButton(label, callback_data=data)])
    rows.append([InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_menu")])
    return InlineKeyboardMarkup(rows)


# ── Persistent bottom bar (stays on screen until removed) ───────

NEW_CHAT_LABEL = "💕 New Anonymous Chat!"
BROWSE_LABEL = "🎉 Browse People"
NEARBY_LABEL = "🧭 Nearby People"
SECURE_LABEL = "🔒 Secure Chat"
SECURE_ON_LABEL = "🔓 Secure Chat ON"
CONTACT_PROFILE_LABEL = "👤 Contact Profile"
END_CHAT_LABEL = "End Chat"
DELETE_LABEL = "🗑 Delete Messages"
# The bar is only replaced when a message goes out, so the buttons may still
# wear yesterday's Secure Chat spelling — recognise every variant.
SECURE_LABELS = (SECURE_LABEL, SECURE_ON_LABEL)


def main_reply_keyboard(
    secure: bool = False, in_chat: bool = False
) -> ReplyKeyboardMarkup:
    """The always-visible bar under the message field (MeChat layout).

    While a chat is active the chat controls show; otherwise the three
    discovery buttons show — never all seven at once.
    """
    secure_label = SECURE_ON_LABEL if secure else SECURE_LABEL
    if in_chat:
        rows = [
            [KeyboardButton(secure_label), KeyboardButton(CONTACT_PROFILE_LABEL)],
            [KeyboardButton(END_CHAT_LABEL), KeyboardButton(DELETE_LABEL)],
        ]
    else:
        rows = [
            [KeyboardButton(NEW_CHAT_LABEL)],
            [KeyboardButton(BROWSE_LABEL), KeyboardButton(NEARBY_LABEL)],
        ]
    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        is_persistent=True,
    )


# ── Per-search partner choice (Random only — gender search is off) ─

def search_choice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Random(Free)", callback_data="search_random")],
    ])


# ── Profile ──────────────────────────────────────────────────────

def profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("❤️ View Likers", callback_data="view_likers"),
            InlineKeyboardButton("📇 Contact List", callback_data="contacts"),
        ],
        [
            InlineKeyboardButton("🚫 Blocked Users", callback_data="blocked_list"),
            InlineKeyboardButton("⚙️ Advanced Settings", callback_data="settings"),
        ],
        [
            InlineKeyboardButton("📊 Stats", callback_data="stats"),
            InlineKeyboardButton("💎 Credits", callback_data="credit_menu"),
        ],
        [
            InlineKeyboardButton("📝 Edit Profile Information", callback_data="settings"),
        ],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="back_menu")],
    ])


def blocked_users_keyboard(users) -> InlineKeyboardMarkup:
    """🚫 Blocked Users list with per-user Unblock buttons."""
    def label(u) -> str:
        # Never show @username (a direct account link) — name or the
        # anonymous 6-digit profile ID only.
        if getattr(u, "name", None):
            return f"🚫 {u.name}"
        if getattr(u, "public_id", 0):
            return f"🚫 ID {u.public_id}"
        return "🚫 Stranger"

    rows = [
        [InlineKeyboardButton(label(u), callback_data=f"unblock_{u.user_id}")]
        for u in users[:20]
    ]
    rows.append([InlineKeyboardButton("⬅️ Back to Profile", callback_data="my_profile")])
    return InlineKeyboardMarkup(rows)


def browse_menu_keyboard() -> InlineKeyboardMarkup:
    """🌟 'Who do you want to see?' — MeChat-style browse categories."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Ready to Chat", callback_data="brw_available")],
        [InlineKeyboardButton("⭐ People My Age", callback_data="brw_myage")],
        [
            InlineKeyboardButton("💕 Ready to Chat", callback_data="brw_ready"),
            InlineKeyboardButton("🙋 New Members 🙋", callback_data="brw_new"),
        ],
        [InlineKeyboardButton("👀 Recent Chats 👀", callback_data="brw_recent")],
        [InlineKeyboardButton("Popular People ❤️", callback_data="brw_popular")],
        [InlineKeyboardButton("🌍 Everyone", callback_data="brw_all")],
    ])


def promo_keyboard(bot_username: str) -> InlineKeyboardMarkup:
    """Pinned-style promo: start a chat and grab the free coin."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Start Random Chat", callback_data="search_random")]
    ])


def back_to_profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back to Profile", callback_data="my_profile")]
    ])


# ── Credits / coin shop ──────────────────────────────────────────

# (coins, stars, is_vip)
COIN_PLANS = [
    (280, 100, False),
    (500, 151, False),
    (1300, 222, False),
    (2500, 318, False),
    (6200, 740, True),
]


def credit_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("🎁 Refer Friends (Free Coin)", callback_data="show_refer")]]
    for coins, stars, vip in COIN_PLANS:
        label = f"👑 {coins} Coins VIP → ⭐{stars}" if vip else f"🪙 {coins} Coins → ⭐{stars}"
        rows.append([InlineKeyboardButton(label, callback_data=f"buy_{stars}_{coins}")])
    rows.append([InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_menu")])
    return InlineKeyboardMarkup(rows)


def back_to_credit_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back to Credits", callback_data="credit_menu")]
    ])


# ── Settings ─────────────────────────────────────────────────────

def settings_keyboard(
    reminder_on: bool = False, vip: bool = False
) -> InlineKeyboardMarkup:
    reminder_label = (
        "⏰ Daily Reminder: ON ✅" if reminder_on else "⏰ Daily Reminder: OFF"
    )
    rows = [
        [InlineKeyboardButton("✏️ Change Name", callback_data="change_name")],
        [InlineKeyboardButton("🎂 Change Age", callback_data="change_age")],
        [InlineKeyboardButton("🏙 Change City", callback_data="change_city")],
        [InlineKeyboardButton("🔄 Change Gender", callback_data="change_gender")],
        [InlineKeyboardButton("🌍 Change Country", callback_data="change_country")],
    ]
    if vip:
        # 👑 choosing who to chat with is a VIP-only option
        rows.append(
            [InlineKeyboardButton(
                "💕 Change Partner Preference", callback_data="change_pref"
            )]
        )
    rows += [
        [InlineKeyboardButton("📷 Set Profile Photo", callback_data="set_photo")],
        [InlineKeyboardButton("📝 Edit Bio", callback_data="edit_bio")],
        [InlineKeyboardButton("🎯 Edit Interests", callback_data="edit_interests")],
        [InlineKeyboardButton("🗣 Edit Languages", callback_data="edit_langs")],
        [InlineKeyboardButton("🔎 Find by ID", callback_data="find_id")],
        [InlineKeyboardButton(reminder_label, callback_data="reminder_toggle")],
        [InlineKeyboardButton("🪩 Get Verified", callback_data="verify_start")],
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_menu")],
    ]
    return InlineKeyboardMarkup(rows)


# ── In-chat controls ────────────────────────────────────────────

def chat_keyboard(secure: bool = False) -> InlineKeyboardMarkup:
    """
    MeChat-style in-chat bar: Secure Chat / Contact Profile,
    End Chat / Report, plus 🎮 Play Games (Quiz Battle vs partner).
    `secure` reflects the Secure Chat toggle so the button shows its
    current state.
    """
    secure_label = "🔓 Secure Chat ON" if secure else "🔐 Secure Chat"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(secure_label, callback_data="secure_chat"),
            InlineKeyboardButton("👤 Contact Profile", callback_data="pview"),
        ],
        [
            InlineKeyboardButton("🛑 End Chat", callback_data="end_chat"),
            InlineKeyboardButton("🚩 Report", callback_data="report_partner"),
        ],
        [InlineKeyboardButton("🎮 Play Games", callback_data="games_menu")],
    ])


# ── Searching controls ──────────────────────────────────────────

def searching_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel Search", callback_data="cancel_search")]
    ])


# ── Nearby / contacts / ID lookup lists ─────────────────────────

def user_list_keyboard(users, empty_callback="back_menu") -> InlineKeyboardMarkup:
    """
    Buttons for a list of users. Each item must expose .user_id.
    Used by Nearby, Contacts and the ID search results.
    """
    if not users:
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Back to Menu", callback_data=empty_callback)]]
        )
    rows = [
        [InlineKeyboardButton(label, callback_data=f"view_{user.user_id}")]
        for label, user in users
    ]
    rows.append([InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_menu")])
    return InlineKeyboardMarkup(rows)


def share_location_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📍 Share My Location", callback_data="share_location")],
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_menu")],
    ])


def nearby_list_keyboard(users, empty_callback="nearby") -> InlineKeyboardMarkup:
    """
    Nearby results with a 🔄 Refresh (rescans — someone may have just
    shared their location) and a 📍 re-share shortcut when empty.
    """
    if not users:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data=empty_callback)],
            [InlineKeyboardButton("📍 Share My Location", callback_data="share_location")],
            [InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_menu")],
        ])
    rows = [
        [InlineKeyboardButton(label, callback_data=f"view_{user.user_id}")]
        for label, user in users
    ]
    rows.append([InlineKeyboardButton("📋 Send Message to List", callback_data="browse_msg")])
    rows.append([InlineKeyboardButton("🔄 Refresh", callback_data=empty_callback)])
    rows.append([InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_menu")])
    return InlineKeyboardMarkup(rows)


# ── Someone else's profile (viewed by ID / Nearby / Contacts) ──

def profile_view_keyboard(
    target_id: int, liked: bool, notify: bool = False, back: str = "back_list"
) -> InlineKeyboardMarkup:
    like_label = "💔 Unlike" if liked else "❤️ Like"
    notify_label = "🔕 Alerts off" if notify else "🔔 Notify me when chat ends"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(like_label, callback_data=f"like_toggle_{target_id}")],
        [
            InlineKeyboardButton(
                f"📨 Direct Message ({DIRECT_MESSAGE_COST} 🪙)",
                callback_data=f"dm_{target_id}",
            ),
            InlineKeyboardButton(
                f"📨 Chat Request ({CHAT_REQUEST_COST} 🪙)",
                callback_data=f"req_chat_{target_id}",
            ),
        ],
        [
            InlineKeyboardButton("🔒 Block User", callback_data=f"block_{target_id}"),
            InlineKeyboardButton("🚩 Report User", callback_data=f"rpt_{target_id}"),
        ],
        [
            InlineKeyboardButton("➕ Add to Contacts", callback_data=f"addc_{target_id}"),
            InlineKeyboardButton(notify_label, callback_data=f"notify_{target_id}"),
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data=back)],
    ])


# ── Incoming chat request ───────────────────────────────────────

def request_keyboard(from_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Accept", callback_data=f"req_yes_{from_id}"),
            InlineKeyboardButton("❌ Decline", callback_data=f"req_no_{from_id}"),
        ]
    ])


def view_request_keyboard(from_id: int) -> InlineKeyboardMarkup:
    """Shown on the request notification — opens the accept/decline buttons."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👀 View Chat Request", callback_data=f"req_view_{from_id}")]
    ])


def viewed_by_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Attached to the "someone viewed your profile" toast."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✨🔥 View Profile", callback_data=f"view_{user_id}")]
    ])


# ── Browse People ───────────────────────────────────────────────

def browse_keyboard(has_more: bool, pairs=()) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(label, callback_data=f"view_{user.user_id}")]
        for label, user in pairs
    ]
    # Reference layout: three full-width options, always shown together.
    rows.append([InlineKeyboardButton("➡️ View More List", callback_data="browse_more")])
    rows.append([InlineKeyboardButton("✨ View Profiles by Swiping", callback_data="browse_swipe")])
    rows.append([InlineKeyboardButton("📋 Send Message to List", callback_data="browse_msg")])
    rows.append([InlineKeyboardButton("🌟 Change Category", callback_data="browse_menu")])
    rows.append([InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_menu")])
    return InlineKeyboardMarkup(rows)


def swipe_keyboard(index: int, total: int, target_id: int, liked: bool) -> InlineKeyboardMarkup:
    like_label = "💔 Unlike" if liked else "❤️ Like"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("◀️ Prev", callback_data=f"swipe_{max(0, index - 1)}"),
            InlineKeyboardButton("Next ▶️", callback_data=f"swipe_{min(total - 1, index + 1)}"),
        ],
        [
            InlineKeyboardButton(like_label, callback_data=f"like_toggle_{target_id}"),
            InlineKeyboardButton("👁 Open Profile", callback_data=f"view_{target_id}"),
        ],
        [InlineKeyboardButton("⬅️ Back to List", callback_data="browse_list")],
    ])


# ── VIP ─────────────────────────────────────────────────────────

# (days, price_in_INR) — UPI / PhonePe VIP plans
UPI_VIP_PLANS = [
    (3, 30),
    (7, 60),
    (14, 150),
    (30, 250),   # ⭐ Popular
    (90, 400),   # 👑 Best Value
]
UPI_PLAN_BADGES = {30: "⭐ Popular", 90: "👑 Best Value"}


def vip_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"👑 Upgrade VIP → ⭐{stars}", callback_data=f"buy_{stars}_{coins}")]
        for coins, stars, is_vip in COIN_PLANS
        if is_vip
    ]
    rows.append([
        InlineKeyboardButton(
            "📱 Buy VIP via UPI / PhonePe", callback_data="upi_menu"
        )
    ])
    rows.append([InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_menu")])
    return InlineKeyboardMarkup(rows)


def upi_plan_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for days, price in UPI_VIP_PLANS:
        badge = UPI_PLAN_BADGES.get(days)
        label = f"{days} Days — ₹{price}" + (f" · {badge}" if badge else "")
        rows.append([
            InlineKeyboardButton(label, callback_data=f"upi_plan_{days}")
        ])
    rows.append([InlineKeyboardButton("⬅️ Go Back", callback_data="vip")])
    return InlineKeyboardMarkup(rows)


def upi_paid_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ I Have Paid", callback_data="upi_paid")],
        [InlineKeyboardButton("⬅️ Go Back", callback_data="upi_menu")],
    ])


# ── Verification ────────────────────────────────────────────────

def verify_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👦 Verify as Boy", callback_data="verify_boy"),
            InlineKeyboardButton("👧 Verify as Girl", callback_data="verify_girl"),
        ],
        [InlineKeyboardButton("⬅️ Back to Settings", callback_data="settings")],
    ])


# ── Forced channel subscription ─────────────────────────────────

def force_join_keyboard(channel_link: str) -> InlineKeyboardMarkup:
    """Join-channel gate: open the channel, then confirm you've joined."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Join Channel", url=channel_link)],
        [InlineKeyboardButton("✅ I've Joined", callback_data="joined_check")],
    ])
