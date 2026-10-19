"""
Telegram Random Chat Bot — 🎮 Mini-games

Pure game logic + question banks. No Telegram imports here, so every rule
is unit-testable. bot.py renders these through inline keyboards with
Skip / Replay / Exit controls.

Games:
  💗 Would You Rather   — pick between two options
  🎭 Truth or Dare      — truth/dare prompt generator
  🧠 Quiz Battle       — 5-question quiz (solo vs bot, or vs a partner)
  😂 Emoji Guess       — guess the phrase from emojis
  ⚡ Rapid-Fire        — 10 quick yes/no questions
  🔢 Guess the Number  — higher/lower number hunt (1..100)
  💞 Friendship Quiz   — fun friendship questions with a final score
"""

import random
from dataclasses import dataclass
from typing import Optional


# ═══════════════════════════════════════════════════════════════════
#  💗 Would You Rather
# ═══════════════════════════════════════════════════════════════════

WOULD_YOU_RATHER: list[dict] = [
    {"a": "Always be 10 minutes late 🕰", "b": "Always be 20 minutes early ⏰"},
    {"a": "Only eat pizza for a year 🍕", "b": "Only eat salad for a year 🥗"},
    {"a": "Fly like a bird 🕊", "b": "Be invisible for a day 👻"},
    {"a": "Live by the beach 🏖", "b": "Live in the mountains 🏔"},
    {"a": "Have unlimited money 💰", "b": "Have unlimited time ⏳"},
    {"a": "Always whisper 🤫", "b": "Always shout 📢"},
    {"a": "Never use a phone again 📵", "b": "Never watch TV/movies again 📺"},
    {"a": "Be famous 🌟", "b": "Be secretly rich 💎"},
    {"a": "Travel the world ✈️", "b": "Stay home with loved ones 🏡"},
    {"a": "Speak every language 🌍", "b": "Play every instrument 🎸"},
    {"a": "Have a rewind button ⏪", "b": "Have a pause button ⏸"},
    {"a": "Find true love 💘", "b": "Find a hidden treasure chest 🗺"},
    {"a": "Always be too hot ☀️", "b": "Always be too cold ❄️"},
    {"a": "Eat cake for breakfast 🎂", "b": "Eat breakfast for dinner 🍳"},
    {"a": "Have wings 🦋", "b": "Have a mermaid tail 🧜"},
]


# ═══════════════════════════════════════════════════════════════════
#  🎭 Truth or Dare
# ═══════════════════════════════════════════════════════════════════

TRUTHS: list[str] = [
    "What's the most embarrassing song on your playlist? 🎵",
    "What's a silly fear you have? 😱",
    "What's the last thing you Googled? 🔍",
    "What's your weirdest food combination you actually like? 🍕+?",
    "Have you ever pretended to be busy to avoid someone? 🙈",
    "What's the funniest nickname you've ever had? 🏷",
    "What's something you still do that's meant for kids? 🧸",
    "What's your phone's battery percentage right now? 📱",
    "What's the last lie you told (keep it harmless)? 😇",
    "If you could swap lives with anyone for a day, who? 🔄",
    "What's your guilty-pleasure TV show? 📺",
    "What's the silliest thing you've cried about? 😢",
]

DARES: list[str] = [
    "Compliment yourself out loud right now! 🥰",
    "Do your best celebrity impression for 10 seconds! 🌟",
    "Say 'I'm awesome' in your funniest voice! 🎭",
    "Strike a superhero pose and describe it! 🦸",
    "Send a 😂 emoji to the last person you texted!",
    "Describe your day as a movie trailer voice! 🎬",
    "Pretend you're a robot for the next 15 seconds! 🤖",
    "Invent a new dance move and name it! 💃",
    "Say three nice things about the person you're chatting with! 💬",
    "Do your best animal sound! 🐔",
    "Talk like a pirate for the next message! 🏴‍☠️",
    "Name 5 things in the room within 5 seconds! 🕐",
]


# ═══════════════════════════════════════════════════════════════════
#  🧠 Quiz Battle / general quiz bank
# ═══════════════════════════════════════════════════════════════════

@dataclass
class Question:
    q: str
    options: list[str]
    answer: int                     # index into options
    fact: str = ""                  # shown after answering


QUIZ_BANK: list[Question] = [
    Question("Which planet is known as the Red Planet?", ["Venus", "Mars", "Jupiter", "Saturn"], 1, "Mars looks red because of iron oxide on its surface."),
    Question("How many continents are there on Earth?", ["5", "6", "7", "8"], 2, "Africa, Antarctica, Asia, Australia, Europe, North & South America."),
    Question("What is the largest ocean on Earth?", ["Atlantic", "Indian", "Arctic", "Pacific"], 3, "The Pacific covers more area than all land combined."),
    Question("Which gas do plants absorb from the air?", ["Oxygen", "Nitrogen", "Carbon dioxide", "Helium"], 2, "Plants take in CO₂ and release oxygen."),
    Question("What's the capital of Japan?", ["Seoul", "Tokyo", "Beijing", "Bangkok"], 1, "Tokyo has been Japan's capital since 1868."),
    Question("How many days are in a leap year?", ["364", "365", "366", "367"], 2, "February gets a 29th day every 4 years."),
    Question("Which is the longest river in the world?", ["Amazon", "Nile", "Yangtze", "Danube"], 1, "The Nile stretches about 6,650 km."),
    Question("What is H₂O commonly known as?", ["Salt", "Water", "Sugar", "Oxygen"], 1, "Two hydrogen atoms + one oxygen = water."),
    Question("Which animal is known as man's best friend?", ["Cat", "Horse", "Dog", "Parrot"], 2, "Dogs have been companions for thousands of years."),
    Question("How many minutes are in an hour?", ["50", "55", "60", "70"], 2, "60 minutes make one hour — easy!"),
    Question("Which colour is made by mixing red and white?", ["Purple", "Pink", "Orange", "Brown"], 1, "Red + white = pink."),
    Question("What do bees collect from flowers?", ["Sand", "Water", "Pollen", "Stones"], 2, "Bees collect pollen and nectar to make honey."),
]


# ═══════════════════════════════════════════════════════════════════
#  😂 Emoji Guess
# ═══════════════════════════════════════════════════════════════════

EMOJI_RIDDLES: list[dict] = [
    {"emojis": "🌍🍕", "options": ["World Pizza Day", "Pizza Planet", "Global Food", "Italian Trip"], "answer": 1, "hint": "Buzz Lightyear's favourite place"},
    {"emojis": "🧊🍦", "options": ["Cold Cream", "Ice Cream", "Frozen Milk", "Snow Cone"], "answer": 1, "hint": "A summer treat"},
    {"emojis": "👁🌫", "options": ["Eye of the Storm", "Seeing Fog", "Blind Mist", "Clear Vision"], "answer": 0, "hint": "A calm centre of chaos"},
    {"emojis": "⏰💣", "options": ["Time Blast", "Ticking Bomb", "Quick Boom", "Clock Work"], "answer": 1, "hint": "It's about to go off!"},
    {"emojis": "🚗💨", "options": ["Fast & Furious", "Speed Racer", "Car Chase", "Road Trip"], "answer": 1, "hint": "Zoom zoom!"},
    {"emojis": "🌧☂", "options": ["Rainy Day", "Storm Cloud", "Umbrella Weather", "Splash"], "answer": 2, "hint": "Perfect umbrella vibes"},
    {"emojis": "💎👑", "options": ["Royal Jewels", "Diamond Crown", "King's Treasure", "Queen's Gems"], "answer": 1, "hint": "Fit for royalty"},
    {"emojis": "🌙⭐", "options": ["Good Night", "Night Sky", "Moon Star", "Sweet Dreams"], "answer": 3, "hint": "What you text before bed"},
    {"emojis": "🎂🎉", "options": ["Party Time", "New Year", "Birthday Bash", "Congratulations"], "answer": 2, "hint": "Candles and wishes"},
    {"emojis": "☕📖", "options": ["Book Cafe", "Reading Nook", "Coffee Break", "Study Time"], "answer": 0, "hint": "A cosy shop corner"},
    {"emojis": "🏃♀♂", "options": ["Track Meet", "Running Late", "Marathon Duo", "Gym Buddies"], "answer": 2, "hint": "42 km of courage"},
    {"emojis": "🎸🔥", "options": ["Hot Guitar", "Rock Star", "Fire Band", "Concert Night"], "answer": 1, "hint": "Shred that solo"},
]


# ═══════════════════════════════════════════════════════════════════
#  ⚡ Rapid-Fire Questions (yes/no)
# ═══════════════════════════════════════════════════════════════════

RAPID_FIRE: list[str] = [
    "Do you prefer mountains over beaches? ⛰ or 🏖?",
    "Have you ever binge-watched a whole series in one day? 📺",
    "Do you think you could win a staring contest? 👀",
    "Is a hotdog a sandwich? 🌭",
    "Have you ever sent a text to the wrong person? 📱",
    "Do you sing in the shower? 🚿",
    "Would you rather have no internet for a week or no coffee for a week? ☕",
    "Have you ever laughed so hard milk came out of your nose? 🥛",
    "Do you believe in love at first sight? 💘",
    "Is cereal soup? 🥣",
    "Have you ever stayed up all night just because? 🌙",
    "Do you always finish what's on your plate? 🍽",
    "Would you fight 100 duck-sized horses or 1 horse-sized duck? 🦆",
    "Do you prefer texting over calling? 💬",
    "Have you ever danced like nobody was watching? 💃",
]


# ═══════════════════════════════════════════════════════════════════
#  💞 Friendship Quiz
# ═══════════════════════════════════════════════════════════════════

FRIENDSHIP_QUIZ: list[Question] = [
    Question("What makes a great friend?", ["Always agrees", "Listens & cares", "Has money", "Never busy"], 1, "Listening beats everything."),
    Question("Your friend is sad. Best move?", ["Ignore it", "Send a meme", "Check in on them", "Give advice unprompted"], 2, "A simple 'hey, you okay?' means the world."),
    Question("A friend forgets your birthday. You…", ["Block them", "Laugh it off", "Remind them kindly", "Post about it"], 2, "Communication > grudges."),
    Question("What's a friendship red flag?", ["Respect", "Jealousy", "Honesty", "Support"], 1, "Jealousy poisons trust."),
    Question("How do you keep a friendship strong?", ["Talk daily", "Share memes", "Show up when it matters", "Gift expensive things"], 2, "Presence in hard times counts most."),
    Question("Your friend disagrees with you. You…", ["Argue forever", "Listen & discuss", "End the friendship", "Ghost them"], 1, "Healthy disagreement is normal."),
    Question("What builds trust over time?", ["Secrets", "Consistency", "Flattery", "Competition"], 1, "Showing up, again and again."),
    Question("Inside jokes are important because they…", ["Exclude others", "Create shared memories", "Show off", "Waste time"], 1, "Shared memory is friendship glue."),
    Question("A real friend will…", ["Only contact you when they need something", "Tell you the truth kindly", "Never disagree with you", "Compete with you"], 1, "Kind honesty is a gift."),
    Question("Best way to celebrate a friend's win?", ["Be jealous", "Say congrats & mean it", "One-up them", "Ignore it"], 1, "Celebrate loudly, always."),
]


# ═══════════════════════════════════════════════════════════════════
#  Game state helpers
# ═══════════════════════════════════════════════════════════════════

GAME_DEFS: dict[str, dict] = {
    "wyr": {"title": "💗 Would You Rather", "kind": "choice2", "pool": WOULD_YOU_RATHER, "shuffle": True},
    "tod": {"title": "🎭 Truth or Dare", "kind": "truthdare", "shuffle": True},
    "quiz": {"title": "🧠 Quiz Battle", "kind": "quiz", "pool": QUIZ_BANK, "size": 5, "shuffle": True},
    "emoji": {"title": "😂 Emoji Guess", "kind": "quiz", "pool": EMOJI_RIDDLES, "size": 5, "shuffle": True},
    "rapid": {"title": "⚡ Rapid-Fire Questions", "kind": "yesno", "pool": RAPID_FIRE, "size": 10, "shuffle": True},
    "num": {"title": "🔢 Guess the Number", "kind": "number", "low": 1, "high": 100, "tries": 7},
    "friend": {"title": "💞 Friendship Quiz", "kind": "quiz", "pool": FRIENDSHIP_QUIZ, "size": 5, "shuffle": True},
}

GAME_MENU_ORDER = ["wyr", "tod", "quiz", "emoji", "rapid", "num", "friend"]


def new_game(game_id: str) -> Optional[dict]:
    """Create a fresh session for one of the mini-games."""
    spec = GAME_DEFS.get(game_id)
    if not spec:
        return None
    kind = spec["kind"]
    session: dict = {
        "game": game_id,
        "kind": kind,
        "score": 0,
        "round": 0,
        "done": False,
    }
    if kind == "choice2":
        pool = list(spec["pool"])
        random.shuffle(pool)
        session["questions"] = pool
        session["round"] = 0
    elif kind == "truthdare":
        truths = list(TRUTHS)
        dares = list(DARES)
        random.shuffle(truths)
        random.shuffle(dares)
        session["truths"] = truths
        session["dares"] = dares
        session["t_i"] = 0
        session["d_i"] = 0
        session["await"] = "pick"     # pick -> truth/dare buttons
    elif kind == "quiz":
        pool = list(spec["pool"])
        random.shuffle(pool)
        session["questions"] = pool[: spec.get("size", len(pool))]
        session["total"] = len(session["questions"])
    elif kind == "yesno":
        pool = list(spec["pool"])
        random.shuffle(pool)
        session["questions"] = pool[: spec.get("size", len(pool))]
        session["total"] = len(session["questions"])
    elif kind == "number":
        session["secret"] = random.randint(spec["low"], spec["high"])
        session["tries"] = spec["tries"]
        session["low"] = spec["low"]
        session["high"] = spec["high"]
        session["last_guess"] = None
    return session


def _q_get(q, key, default=None):
    """Read a field from a Question dataclass or a plain dict riddle."""
    if isinstance(q, dict):
        return q.get(key, default)
    return getattr(q, key, default)


def current_question(session: dict):
    """The active question payload for quiz / emoji / yesno / wyr sessions."""
    kind = session.get("kind")
    if kind in ("choice2", "quiz", "yesno"):
        qs = session.get("questions", [])
        if session["round"] >= len(qs):
            return None
        return qs[session["round"]]
    return None


def answer_quiz(session: dict, option_index: int) -> tuple[bool, str]:
    """Record an answer for the active quiz/emoji question.

    Returns (was_correct, explanation). Auto-advances the round.
    """
    q = current_question(session)
    if q is None:
        return False, "That round is over — tap Replay to start again."
    correct = int(option_index) == int(_q_get(q, "answer", -1))
    if correct:
        session["score"] += 1
    session["round"] += 1
    fact = _q_get(q, "fact", "") or _q_get(q, "hint", "") or ""
    if session["round"] >= session.get("total", len(session.get("questions", []))):
        session["done"] = True
    return correct, fact


def answer_yesno(session: dict, said_yes: bool) -> None:
    """Rapid-fire: every answer advances (no right/wrong — it's opinion)."""
    session["round"] += 1
    session["score"] += 1  # participation score
    total = session.get("total", 0)
    if session["round"] >= total:
        session["done"] = True


def pick_truth_or_dare(session: dict, want_truth: bool) -> str:
    """Return the next truth/dare prompt and advance its index."""
    if want_truth:
        i = session.get("t_i", 0)
        pool = session.get("truths") or list(TRUTHS)
        prompt = pool[i % len(pool)]
        session["t_i"] = i + 1
    else:
        i = session.get("d_i", 0)
        pool = session.get("dares") or list(DARES)
        prompt = pool[i % len(pool)]
        session["d_i"] = i + 1
    session["round"] += 1
    session["score"] += 1
    return prompt


def number_feedback(session: dict, guess: int) -> str:
    """Apply a Guess-the-Number guess and return the hint line."""
    secret = session["secret"]
    session["last_guess"] = guess
    session["tries"] = max(0, session.get("tries", 0) - 1)
    if guess == secret:
        session["done"] = True
        session["score"] = session.get("tries", 0) + 1  # more tries left = better
        return "🎉🎉 CORRECT! You found it!"
    if session["tries"] <= 0:
        session["done"] = True
        return f"⏰ Out of tries! The number was **{secret}**."
    return "📈 Too high!" if guess > secret else "📉 Too low!"


def skip_round(session: dict) -> bool:
    """Advance past the current round. Returns False when already done."""
    if session.get("done"):
        return False
    kind = session.get("kind")
    if kind == "number":
        # re-roll a fresh number instead of skipping one guess
        session["secret"] = random.randint(session.get("low", 1), session.get("high", 100))
        session["tries"] = GAME_DEFS["num"]["tries"]
        session["last_guess"] = None
        return True
    total = session.get("total")
    if total is None:
        # wyr / truthdare are endless until Exit
        session["round"] += 1
        return True
    session["round"] += 1
    if session["round"] >= total:
        session["done"] = True
    return True


def score_line(session: dict) -> str:
    kind = session.get("kind")
    if kind == "number":
        return f"🔢 Tries left: {session.get('tries', 0)}"
    total = session.get("total")
    if total:
        return f"⭐ Score: {session.get('score', 0)} / {total}"
    return f"⭐ Rounds played: {session.get('round', 0)}"


# ═══════════════════════════════════════════════════════════════════
#  🧠 Quiz Battle (2-player) helpers
# ═══════════════════════════════════════════════════════════════════

BATTLE_SIZE = 5


def battle_questions() -> list[dict]:
    pool = list(QUIZ_BANK)
    random.shuffle(pool)
    picked = pool[:BATTLE_SIZE]
    return [
        {"q": q.q, "options": list(q.options), "answer": q.answer}
        for q in picked
    ]


def battle_answer(session: dict, uid: int, option_index: int) -> tuple[bool, bool]:
    """Record `uid`'s answer to the current battle question.

    Returns (was_correct, battle_finished). Turns alternate between the
    two players for each question; after the last answer the battle ends.
    """
    if session.get("done"):
        return False, True
    qi = session["qi"]
    questions = session["questions"]
    if qi >= len(questions):
        session["done"] = True
        return False, True
    q = questions[qi]
    correct = int(option_index) == int(q["answer"])
    if correct:
        key = str(uid)
        session["score"][key] = session.get("score", {}).get(key, 0) + 1
    session["answers"][f"{qi}:{uid}"] = int(option_index)
    a, b = session["a"], session["b"]
    if session["turn"] == a:
        session["turn"] = b
    else:
        session["turn"] = a
        session["qi"] = qi + 1
        if session["qi"] >= len(questions):
            session["done"] = True
    return correct, bool(session.get("done"))


def battle_result(session: dict) -> dict:
    """{a_score, b_score, winner_id|None} — None means a draw."""
    a = session["a"]
    b = session["b"]
    sa = session.get("score", {}).get(str(a), 0)
    sb = session.get("score", {}).get(str(b), 0)
    winner = None
    if sa > sb:
        winner = a
    elif sb > sa:
        winner = b
    return {"a_score": sa, "b_score": sb, "winner_id": winner, "a": a, "b": b}
