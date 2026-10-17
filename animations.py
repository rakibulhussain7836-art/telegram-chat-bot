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
# Continuous emoji cycle used on profile / match cards.
CARD_EMOJIS = ["🙂", "😉", "😊", "🥰", "😘", "😻", "💫", "✨"]


def progress_bar(percent: int, width: int = 10) -> str:
    """A unicode progress bar, e.g. ▰▱▱▱▱▱▱▱▱▱."""
    filled = max(0, min(width, round(percent * width / 100)))
    return "▰" * filled + "▱" * (width - filled)


def search_frames(queue_size: int = 0, total: int = 6):
    """
    Generator of "matching you with a partner" frames (HTML).

    The caller loops over these forever until a match lands, so the
    searching user always sees a moving emoji animation instead of a
    static wait message.
    """
    for i in range(total):
        emoji = CARD_EMOJIS[i % len(CARD_EMOJIS)]
        radar = RADAR_FRAMES[i % len(RADAR_FRAMES)]
        spin = SPINNER_FRAMES[i % len(SPINNER_FRAMES)]
        queue_line = (
            f"👥 {queue_size} people searching right now"
            if queue_size
            else "🌍 Scanning the world…"
        )
        yield (
            f"{emoji} {radar} <b>Matching you with a partner…</b> {spin}\n\n"
            f"{progress_bar(100 if i == total - 1 else int((i + 1) * 90 / total))}\n"
            f"{queue_line}\n"
            f"⏳ Waiting for a match — it can land any second!"
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


def match_photo_frames(final_text: str) -> list:
    """Match reveal played on a photo card caption (Markdown-safe)."""
    return ["💥", "⚡ **It's a match!** ⚡", "💖 🤝 💖", final_text]


def emoji_cycle_frames(final_text: str, rounds: int = 1) -> list:
    """Continuous emoji cycle that lands on the final card text."""
    frames: list = []
    for _ in range(max(1, rounds)):
        frames.extend(CARD_EMOJIS)
    frames.append(final_text)
    return frames


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
    Returns the last frame that was attempted — or None when the target
    could not be edited (message gone, no edit method), so callers can
    tell a broken target from a finished animation.
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
                return None
        except Exception as e:  # noqa: BLE001 — animation must never break a flow
            if "not modified" in str(e).lower():
                if is_last:
                    return last
                continue
            logger.debug(f"animate_edit skipped: {e}")
            return None
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


async def _edit_frame(target, frame, parse_mode=None, reply_markup=None):
    """One search-frame edit attempt.

    Returns True (shown), False (temporary failure — try again later, e.g.
    flood control) or None (the target is unusable — stop for good).
    """
    try:
        if hasattr(target, "edit_message_text"):
            await target.edit_message_text(
                frame, parse_mode=parse_mode, reply_markup=reply_markup
            )
        elif hasattr(target, "edit_text"):
            await target.edit_text(
                frame, parse_mode=parse_mode, reply_markup=reply_markup
            )
        else:
            return None
        return True
    except Exception as e:  # noqa: BLE001
        msg = str(e).lower()
        if "not modified" in msg:
            return True
        if "flood" in msg or "retry" in msg or "too many" in msg:
            return False
        logger.debug(f"search frame edit skipped: {e}")
        return None


async def animate_search(
    context,
    user_id: int,
    check_match,
    queue_size_fn=None,
    frames: int = 6,
    interval: float = 1.0,
    target=None,
    stop_check=None,
    reply_markup=None,
) -> Optional[int]:
    """
    Continuous "matching you with a partner" animation.

    The emoji frames cycle on `target` FOREVER — re-checking for a match
    after every frame — until one of three things happens:
      • `check_match()` returns a partner id  → that id is returned
      • `stop_check()` turns True            → the user cancelled → None
      • the target rejects the edits          → None

    `reply_markup` (the Cancel Search button) is re-attached on every
    frame so it stays tappable for as long as the search runs.
    Returns the partner id on match, else None.
    """
    if not ANIMATIONS_ENABLED or target is None:
        return None

    pool: list = []
    idx = 0
    while True:
        match_id = check_match()
        if match_id:
            return match_id
        if stop_check is not None and stop_check():
            return None
        if idx >= len(pool):
            pool = list(
                search_frames(
                    queue_size=(queue_size_fn() if queue_size_fn else 0),
                    total=frames,
                )
            )
            idx = 0
        frame = pool[idx]
        idx += 1
        done = await _edit_frame(
            target, frame, parse_mode="HTML", reply_markup=reply_markup
        )
        if done is None:
            return None  # target rejected the edit — stop animating
        if done is False:
            await asyncio.sleep(max(interval, 2.0))  # flood control — back off
            continue
        await asyncio.sleep(interval)


async def animate_message_caption(
    msg, frames, reply_markup=None, parse_mode=None, interval: float = 0.45
) -> bool:
    """
    Edit an already-sent message's caption through `frames`; the final
    frame carries `reply_markup`. Fail-silent: on any edit failure it
    makes one last attempt to land the finished card (buttons included).
    Returns False only when the message itself cannot be edited.
    """
    frames = list(frames)
    if msg is None or not hasattr(msg, "edit_caption"):
        return False
    if not frames:
        return True
    if not ANIMATIONS_ENABLED:
        frames = frames[-1:]

    for i, frame in enumerate(frames):
        is_last = i == len(frames) - 1
        try:
            await msg.edit_caption(
                caption=frame,
                parse_mode=parse_mode,
                reply_markup=reply_markup if is_last else None,
            )
        except Exception as e:  # noqa: BLE001
            logger.debug(f"caption frame skipped: {e}")
            if not is_last:
                # A mid-frame edit hiccup — land the finished card instead
                # (buttons included) so the message is never left half-typed.
                try:
                    await msg.edit_caption(
                        caption=frames[-1],
                        parse_mode=parse_mode,
                        reply_markup=reply_markup,
                    )
                    return True
                except Exception as e2:  # noqa: BLE001
                    logger.debug(f"caption fallback skipped: {e2}")
            return False  # even the finished card could not be landed
        if not is_last:
            await asyncio.sleep(interval)
    return True


async def animate_photo_card(
    bot,
    chat_id: int,
    photo,
    frames,
    reply_markup=None,
    parse_mode=None,
    interval: float = 0.45,
    on_sent=None,
) -> bool:
    """
    Send `photo` with the first frame as its caption, then 'type' through
    the remaining frames — the buttons land with the final frame, so the
    whole card is ONE message (photo + info + buttons).

    `on_sent` (if given) is called with the sent Message so the caller can
    remember where the card lives (needed to flip it in place later).

    Returns True when the photo went out (callers may then skip their
    text fallback), False when the photo could not be sent.
    """
    frames = list(frames)
    if not frames:
        return False

    if not ANIMATIONS_ENABLED:
        try:
            msg = await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=frames[-1],
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
            if on_sent is not None:
                on_sent(msg)
            return True
        except Exception as e:  # noqa: BLE001
            logger.debug(f"photo card skipped: {e}")
            return False

    try:
        msg = await bot.send_photo(
            chat_id=chat_id, photo=photo, caption=frames[0], parse_mode=parse_mode
        )
    except Exception as e:  # noqa: BLE001
        logger.debug(f"photo card send skipped: {e}")
        return False
    if msg is None:
        return True  # delivered, but there is no message object to animate
    if on_sent is not None:
        on_sent(msg)
    await animate_message_caption(
        msg, frames[1:], reply_markup=reply_markup, parse_mode=parse_mode,
        interval=interval,
    )
    return True
