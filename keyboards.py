"""
Telegram Random Chat Bot — Keyboard Layouts

All inline keyboard builders live here for clean separation.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from database import GIRL_SEARCH_COST


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
            InlineKeyboardButton("👤 My Profile", callback_data="my_profile"),
            InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
        ],
        [
            InlineKeyboardButton("💎 Credits", callback_data="credit_menu"),
            InlineKeyboardButton("📊 Stats", callback_data="stats"),
        ],
    ])


# ── Per-search partner choice (Random / Guy / Girl) ─────────────

def search_choice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Random (Free)", callback_data="search_random")],
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
        [InlineKeyboardButton("🔄 Change Gender", callback_data="change_gender")],
        [InlineKeyboardButton("🌍 Change Country", callback_data="change_country")],
        [InlineKeyboardButton("💕 Change Partner Preference", callback_data="change_pref")],
        [InlineKeyboardButton("📷 Set Profile Photo", callback_data="set_photo")],
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
    ])


# ── Searching controls ──────────────────────────────────────────

def searching_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel Search", callback_data="cancel_search")]
    ])
