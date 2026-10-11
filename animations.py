"""
Telegram bot animation helpers.

Telegram bots can't stream GIFs of their own UI, so "animations" here means
message-edit choreography: a message is rewritten through a sequence of
frames (radar spinners, progress bars, bounce-in reveals) plus fake
"typing…" chat actions. Everything is fail-silent: if Telegram rejects an
edit (or the target is a test mock), the animation is simply skipped.

Set BOT_ANIMATIONS=0 to disable all animations (used by the test suite).
"""

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

ANIMATIONS_ENABLED = os.getenv("BOT_ANIMATIONS", "1") == "1"

# ── Frame pools ──────────────────────────────────────────────────

RADAR_FRAMES = ["📡", "🌍", "🌐", "🗺️", "🧭", "🛰️", "✈️", "🚀"]
SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
HEART_FRAMES = ["💗", "💖", "💘", "💝", "💕", "💞"]
CONFETTI_FRAMES = ["🎉", "🎊", "✨", "🎉", "🎊", "🪅", "🥳"]
TYPING_ELLIPSIS = ["", ".", "..", "..."]


def progress_bar(percent: int, width: int = 10) -> str:
    """A unicode progress bar, e.g. ▰▱▱▱▱▱▱▱▱▱."""
    filled = max(0, min(width, round(percent * width / 100)))
    return "▰" * filled + "▱" * (width - filled)


def search_frames(queue_size: int = 0, total: int = 6):
    """
    Generator of radar-search frames with a filling progress bar.
    Yields `total` frames; the last one is ~95% full (match can land anytime).
    """
    for i in range(total):
        pct = min(95, int((i + 1) * 95 / total))
        radar = RADAR_FRAMES[i % len(RADAR_FRAMES)]
        spin = SPINNER_FRAMES[i % len(SPINNER_FRAMES)]
        queue_line = (
            f"👥 {queue_size} people searching right now"
            if queue_size
            else "🌍 Scanning the world…"
        )
        yield (
            f"{radar} **Searching for a partner…** {spin}\n\n"
            f"{progress_bar(pct)} {pct}%\n"
            f"{queue_line}\n"
            f"💡 Hang tight — the next frame might be your match!"
        )


def reveal_frames(final_text: str, steps: int = 3):
    """
    Bounce-in reveal: the final text 'types itself in' in a few quick steps.
    """
    yield "✨"
    for i in range(1, steps + 1):
        cut = max(1, len(final_text) * i // steps)
        yield final_text[:cut] + ("▌" if cut < len(final_text) else "")
    yield final_text


def match_frames() -> list:
    return [
        "💥",
        "⚡ **It's a match!** ⚡",
        "💖🤝💖",
    ]


async def animate_edit(target, frames, interval: float = 0.55, parse_mode=None):
    """
    Play `frames` through a message by editing it in place.

    `target` may be a Message (uses .edit_text) or a CallbackQuery
    (uses .edit_message_text). Returns the last frame that was attempted.
    """
    last = None
    if not ANIMATIONS_ENABLED:
        return None
    for frame in frames:
        last = frame
        try:
            if hasattr(target, "edit_message_text"):
                await target.edit_message_text(frame, parse_mode=parse_mode)
            elif hasattr(target, "edit_text"):
                await target.edit_text(frame, parse_mode=parse_mode)
            else:
                return last
        except Exception as e:  # noqa: BLE001 — animation must never break a flow
            logger.debug(f"animate_edit skipped: {e}")
            return last
        await asyncio.sleep(interval)
    return last


async def typing_pulse(bot, chat_id: int, times: int = 3, interval: float = 0.7):
    """Show the 'typing…' status a few times (fake partner activity)."""
    if not ANIMATIONS_ENABLED:
        return
    try:
        from telegram.constants import ChatAction

        for _ in range(times):
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(interval)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"typing_pulse skipped: {e}")


async def celebration_pulse(bot, chat_id: int):
    """Short burst of chat actions for a match moment."""
    if not ANIMATIONS_ENABLED:
        return
    try:
        from telegram.constants import ChatAction

        for _ in range(2):
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(0.35)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"celebration_pulse skipped: {e}")


async def animate_search(
    context,
    user_id: int,
    check_match,
    queue_size_fn=None,
    frames: int = 6,
    interval: float = 0.85,
    target=None,
) -> Optional[int]:
    """
    Animate a partner search: play radar frames on `target`, re-checking for
    a match after every frame. `check_match` returns a partner id or None.

    Returns the partner id on match, else None (search continues in queue).
    """
    if not ANIMATIONS_ENABLED or target is None:
        return None
    for frame in search_frames(
        queue_size=(queue_size_fn() if queue_size_fn else 0), total=frames
    ):
        match_id = check_match()
        if match_id:
            return match_id
        stop = await animate_edit(target, [frame], interval=interval)
        if stop is None:
            return None  # target rejected the edit — stop animating
    return check_match()
