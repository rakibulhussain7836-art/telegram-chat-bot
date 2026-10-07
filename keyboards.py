"""
Telegram Random Chat Bot — Keyboard Layouts

All inline keyboard builders live here for clean separation.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


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
        [InlineKeyboardButton("📊 Stats", callback_data="stats")],
    ])


# ── Settings ─────────────────────────────────────────────────────

def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Change Gender", callback_data="change_gender")],
        [InlineKeyboardButton("🌍 Change Country", callback_data="change_country")],
        [InlineKeyboardButton("💕 Change Partner Preference", callback_data="change_pref")],
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_menu")],
    ])


# ── In-chat controls ────────────────────────────────────────────

def chat_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏭️ Next Partner", callback_data="next_partner"),
            InlineKeyboardButton("🛑 End Chat", callback_data="end_chat"),
        ]
    ])


# ── Searching controls ──────────────────────────────────────────

def searching_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel Search", callback_data="cancel_search")]
    ])
