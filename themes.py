"""
Telegram Random Chat Bot — 🎨 Cosmetic themes

Telegram bots cannot recolor the Telegram UI itself, so a "theme" is a
cosmetic skin applied to the bot's own cards and menus: a header/banner
line, an emoji set and a footer accent. Users unlock themes with coins;
the active theme is stored per user in the database.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    id: str
    name: str
    emoji: str
    cost: int          # coins to unlock (0 = free/default)
    banner: str        # decorative header line
    accent: str        # accent emoji sprinkled around cards


THEMES: dict[str, Theme] = {
    "default": Theme(
        id="default",
        name="🌟 Default",
        emoji="🌟",
        cost=0,
        banner="· · · · · · · · · · · · · · ·",
        accent="✨",
    ),
    "pink_love": Theme(
        id="pink_love",
        name="💗 Pink Love",
        emoji="💗",
        cost=5,
        banner="ʚ♡ɞ ʚ♡ɞ ʚ♡ɞ ʚ♡ɞ ʚ♡ɞ ʚ♡ɞ ʚ♡ɞ",
        accent="💗",
    ),
    "ocean_blue": Theme(
        id="ocean_blue",
        name="🌊 Ocean Blue",
        emoji="🌊",
        cost=5,
        banner="≈ ≈ ≈ ≈ ≈ ≈ ≈ ≈ ≈ ≈ ≈ ≈ ≈ ≈ ≈",
        accent="🌊",
    ),
    "purple_galaxy": Theme(
        id="purple_galaxy",
        name="🌌 Purple Galaxy",
        emoji="🌌",
        cost=8,
        banner="✦ ˚ ✧ ⋆ ✦ ˚ ✧ ⋆ ✦ ˚ ✧ ⋆ ✦ ˚",
        accent="🌌",
    ),
    "midnight_dark": Theme(
        id="midnight_dark",
        name="🌑 Midnight Dark",
        emoji="🌑",
        cost=5,
        banner="━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        accent="🌑",
    ),
    "neon_green": Theme(
        id="neon_green",
        name="💚 Neon Green",
        emoji="💚",
        cost=8,
        banner="▓▒░ ▓▒░ ▓▒░ ▓▒░ ▓▒░ ▓▒░ ▓▒░",
        accent="💚",
    ),
    "sunset_orange": Theme(
        id="sunset_orange",
        name="🌇 Sunset Orange",
        emoji="🌇",
        cost=5,
        banner="▬▬ ▬▬ ▬▬ ▬▬ ▬▬ ▬▬ ▬▬ ▬▬ ▬▬",
        accent="🌇",
    ),
}

BUYABLE_THEMES = [t for t in THEMES.values() if t.cost > 0]


def get_theme(theme_id: str) -> Theme:
    """The theme with `theme_id`, falling back to the default skin."""
    return THEMES.get(theme_id) or THEMES["default"]


def theme_line(user) -> str:
    """Banner line for a user's active theme (used at the top of cards)."""
    theme = get_theme(getattr(user, "theme", "default") or "default")
    return f"{theme.emoji} {theme.banner} {theme.emoji}"


def theme_accent(user) -> str:
    theme = get_theme(getattr(user, "theme", "default") or "default")
    return theme.accent
