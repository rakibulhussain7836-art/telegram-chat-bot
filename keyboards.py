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

from database import CHAT_REQUEST_COST, GIRL_SEARCH_COST


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
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Find a Partner", callback_data="find_partner")],
        [
            InlineKeyboardButton("📍 Nearby", callback_data="nearby"),
            InlineKeyboardButton("🔎 Find by ID", callback_data="find_id"),
        ],
        [
            InlineKeyboardButton("👤 My Profile", callback_data="my_profile"),
            InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
        ],
        [
            InlineKeyboardButton("💎 Credits", callback_data="credit_menu"),
            InlineKeyboardButton("📊 Stats", callback_data="stats"),
        ],
    ])


# ── Persistent bottom bar (stays on screen until removed) ───────

NEW_CHAT_LABEL = "💕 New Anonymous Chat!"
BROWSE_LABEL = "🎉 Browse People"
NEARBY_LABEL = "🧭 Nearby People"


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    """The always-visible bar under the message field."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(NEW_CHAT_LABEL)],
            [KeyboardButton(BROWSE_LABEL), KeyboardButton(NEARBY_LABEL)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


# ── Per-search partner choice (Random / Guy / Girl) ─────────────

def search_choice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Start Random Chat", callback_data="search_random")],
        [
            InlineKeyboardButton("🕺 Chat With Guy (Free)", callback_data="search_guy"),
            InlineKeyboardButton(f"💃 Chat With Girl ({GIRL_SEARCH_COST} 🪙)", callback_data="search_girl"),
        ],
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_menu")],
    ])


# ── Profile ──────────────────────────────────────────────────────

def profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❤️ View Likers", callback_data="view_likers")],
        [InlineKeyboardButton("📇 My Contacts", callback_data="contacts")],
        [
            InlineKeyboardButton("🔍 Find a Partner", callback_data="find_partner"),
            InlineKeyboardButton("💎 Credits", callback_data="credit_menu"),
        ],
        [
            InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
            InlineKeyboardButton("📊 Stats", callback_data="stats"),
        ],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="back_menu")],
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

def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Change Name", callback_data="change_name")],
        [InlineKeyboardButton("🎂 Change Age", callback_data="change_age")],
        [InlineKeyboardButton("🏙 Change City", callback_data="change_city")],
        [InlineKeyboardButton("🔄 Change Gender", callback_data="change_gender")],
        [InlineKeyboardButton("🌍 Change Country", callback_data="change_country")],
        [InlineKeyboardButton("💕 Change Partner Preference", callback_data="change_pref")],
        [InlineKeyboardButton("📷 Set Profile Photo", callback_data="set_photo")],
        [InlineKeyboardButton("🪩 Get Verified", callback_data="verify_start")],
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_menu")],
    ])


# ── In-chat controls ────────────────────────────────────────────

def chat_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏭️ Next Partner", callback_data="next_partner"),
            InlineKeyboardButton("🛑 End Chat", callback_data="end_chat"),
        ],
        [
            InlineKeyboardButton("❤️ Like Partner", callback_data="like_partner"),
            InlineKeyboardButton("🚩 Report Partner", callback_data="report_partner"),
        ],
        [InlineKeyboardButton("➕ Add to Contacts", callback_data="add_contact")],
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


# ── Someone else's profile (viewed by ID / Nearby / Contacts) ──

def profile_view_keyboard(
    target_id: int, liked: bool, notify: bool = False
) -> InlineKeyboardMarkup:
    like_label = "💔 Unlike" if liked else "❤️ Like"
    notify_label = "🔕 Alerts off" if notify else "🔔 Notify me when chat ends"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(like_label, callback_data=f"like_toggle_{target_id}")],
        [
            InlineKeyboardButton("📨 Direct Message", callback_data=f"dm_{target_id}"),
            InlineKeyboardButton(
                f"📨 Chat Request ({CHAT_REQUEST_COST} 🪙)",
                callback_data=f"req_chat_{target_id}",
            ),
        ],
        [
            InlineKeyboardButton("🔒 Block User", callback_data=f"block_{target_id}"),
            InlineKeyboardButton("🚩 Report User", callback_data=f"report_{target_id}"),
        ],
        [
            InlineKeyboardButton("➕ Add to Contacts", callback_data=f"addc_{target_id}"),
            InlineKeyboardButton(notify_label, callback_data=f"notify_{target_id}"),
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_list")],
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
        [InlineKeyboardButton("✨❤️🔥 View Profile", callback_data=f"view_{user_id}")]
    ])


# ── Browse People ───────────────────────────────────────────────

def browse_keyboard(has_more: bool, pairs=()) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(label, callback_data=f"view_{user.user_id}")]
        for label, user in pairs
    ]
    if has_more:
        rows.append([InlineKeyboardButton("➡️ View More List", callback_data="browse_more")])
    rows.append([
        InlineKeyboardButton("✨ View Profiles by Swiping", callback_data="browse_swipe"),
        InlineKeyboardButton("📋 Send Message to List", callback_data="browse_msg"),
    ])
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

def vip_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"👑 Upgrade VIP → ⭐{stars}", callback_data=f"buy_{stars}_{coins}")]
        for coins, stars, is_vip in COIN_PLANS
        if is_vip
    ]
    rows.append([InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_menu")])
    return InlineKeyboardMarkup(rows)


# ── Verification ────────────────────────────────────────────────

def verify_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👦 Verify as Boy", callback_data="verify_boy"),
            InlineKeyboardButton("👧 Verify as Girl", callback_data="verify_girl"),
        ],
        [InlineKeyboardButton("⬅️ Back to Settings", callback_data="settings")],
    ])
