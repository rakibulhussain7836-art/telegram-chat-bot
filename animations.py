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
    Generator of radar-search frames with a filling progress bar (HTML).
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
            f"{radar} <b>Searching for a partner…</b> {spin}\n\n"
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
        "⚡ <b>It's a match!</b> ⚡",
        "💖🤝💖",
    ]


def bounce_frames(final_text: str) -> list:
    """Short sparkle bounce-in for menus and confirmations."""
    return ["✨", "🌟", final_text]


def coin_frames(final_text: str) -> list:
    """Coin shower for credits and payments."""
    return ["🪙", "💰✨", final_text]


def heart_frames(final_text: str) -> list:
    """Heart burst for likes."""
    return ["💗", "💖💘", final_text]


async def animate_edit(
    target, frames, interval: float = 0.55, parse_mode=None, reply_markup=None
):
    """
    Play `frames` through a message by editing it in place.

    `target` may be a Message (uses .edit_text) or a CallbackQuery
    (uses .edit_message_text). `reply_markup` is applied on the final
    frame only. With animations disabled this degrades to a single edit
    of the last frame, so it can replace a plain safe_edit() call.
    Returns the last frame that was attempted.
    """
    frames = list(frames)
    if not frames:
        return None

    if not ANIMATIONS_ENABLED:
        try:
            if hasattr(target, "edit_message_text"):
                await target.edit_message_text(
                    frames[-1], parse_mode=parse_mode, reply_markup=reply_markup
                )
            elif hasattr(target, "edit_text"):
                await target.edit_text(
                    frames[-1], parse_mode=parse_mode, reply_markup=reply_markup
                )
        except Exception:  # noqa: BLE001
            pass
        return frames[-1]

    last = None
    for i, frame in enumerate(frames):
        last = frame
        is_last = i == len(frames) - 1
        try:
            if hasattr(target, "edit_message_text"):
                await target.edit_message_text(
                    frame,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup if is_last else None,
                )
            elif hasattr(target, "edit_text"):
                await target.edit_text(
                    frame,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup if is_last else None,
                )
            else:
                return last
        except Exception as e:  # noqa: BLE001 — animation must never break a flow
            logger.debug(f"animate_edit skipped: {e}")
            return last
        if not is_last:
            await asyncio.sleep(interval)
    return last


async def animated_reply(
    message, frames, interval: float = 0.35, parse_mode=None, reply_markup=None
):
    """
    Reply with a short bounce-in animation: sends the first frame, edits
    through the rest, and puts reply_markup on the final frame.
    With animations disabled it behaves exactly like message.reply_text().
    """
    frames = list(frames)
    if not frames or not hasattr(message, "reply_text"):
        return None

    if not ANIMATIONS_ENABLED:
        return await message.reply_text(
            frames[-1], parse_mode=parse_mode, reply_markup=reply_markup
        )

    try:
        msg = await message.reply_text(frames[0], parse_mode=parse_mode)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"animated_reply skipped: {e}")
        return None
    if not hasattr(msg, "edit_text"):
        return msg

    for frame in frames[1:-1]:
        try:
            await msg.edit_text(frame, parse_mode=parse_mode)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"animated_reply cut short: {e}")
            return msg
        await asyncio.sleep(interval)
    try:
        await msg.edit_text(
            frames[-1], parse_mode=parse_mode, reply_markup=reply_markup
        )
    except Exception as e:  # noqa: BLE001
        logger.debug(f"animated_reply final frame skipped: {e}")
    return msg


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
        stop = await animate_edit(
            target, [frame], interval=interval, parse_mode="HTML"
        )
        if stop is None:
            return None  # target rejected the edit — stop animating
    return check_match()
