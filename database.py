"""
Telegram Random Chat Bot — Database & User Models

Keeps all state in memory and mirrors it to a SQLite file (DB_PATH,
default ./bot.db) so users, coins and referrals survive restarts.
Set DB_PATH="" to run fully in memory (used by the test suite).
Tracks user profiles, active sessions, matchmaking queue, coins,
referrals, likes and reports.
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import atexit
import json
import os
import sqlite3
import threading
import time

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


class Gender(Enum):
    MALE = "male"
    FEMALE = "female"
    ANY = "any"  # preference: match with anyone


class ChatState(Enum):
    IDLE = "idle"              # registered but not searching
    SEARCHING = "searching"    # in the matchmaking queue
    CHATTING = "chatting"      # actively paired with someone


# ── Economy / moderation settings ────────────────────────────────
STARTING_COINS = 10        # free coins for every new user
REFERRAL_REWARD = 15       # coins earned by the referrer per friend
REFERRED_BONUS = 5         # extra coins for the newly referred friend
GIRL_SEARCH_COST = 1       # coins per "Chat With Girl" search
BAN_REPORT_THRESHOLD = 5   # unique reports before an account is restricted


@dataclass
class UserProfile:
    user_id: int
    username: Optional[str] = None
    gender: Optional[Gender] = None
    country: Optional[str] = None
    preferred_gender: Gender = Gender.ANY
    state: ChatState = ChatState.IDLE
    partner_id: Optional[int] = None
    registered_at: float = field(default_factory=time.time)
    total_chats: int = 0
    # ── Economy ──
    coins: int = STARTING_COINS
    referral_count: int = 0
    referral_earned: int = 0
    referred_by: Optional[int] = None
    # ── Likes ──
    likes: int = 0
    liked_by: set[int] = field(default_factory=set)
    # ── Moderation ──
    reports: set[int] = field(default_factory=set)   # users who reported me
    blocked: set[int] = field(default_factory=set)   # users I reported/blocked
    banned: bool = False
    # ── Active search filter (chosen per search) ──
    search_pref: Optional[Gender] = None
    # ── Profile photo (Telegram file_id, sent to partner on match) ──
    photo_file_id: Optional[str] = None


def _user_to_json(user: UserProfile) -> str:
    """Serialize a profile for the SQLite store."""
    return json.dumps(
        {
            "user_id": user.user_id,
            "username": user.username,
            "gender": user.gender.value if user.gender else None,
            "country": user.country,
            "preferred_gender": user.preferred_gender.value,
            "state": user.state.value,
            "partner_id": user.partner_id,
            "registered_at": user.registered_at,
            "total_chats": user.total_chats,
            "coins": user.coins,
            "referral_count": user.referral_count,
            "referral_earned": user.referral_earned,
            "referred_by": user.referred_by,
            "likes": user.likes,
            "liked_by": sorted(user.liked_by),
            "reports": sorted(user.reports),
            "blocked": sorted(user.blocked),
            "banned": user.banned,
            "search_pref": user.search_pref.value if user.search_pref else None,
            "photo_file_id": user.photo_file_id,
        }
    )


def _user_from_json(data: str) -> UserProfile:
    d = json.loads(data)
    return UserProfile(
        user_id=d["user_id"],
        username=d["username"],
        gender=Gender(d["gender"]) if d["gender"] else None,
        country=d["country"],
        preferred_gender=Gender(d["preferred_gender"]),
        state=ChatState(d["state"]),
        partner_id=d["partner_id"],
        registered_at=d["registered_at"],
        total_chats=d["total_chats"],
        coins=d["coins"],
        referral_count=d["referral_count"],
        referral_earned=d["referral_earned"],
        referred_by=d["referred_by"],
        likes=d["likes"],
        liked_by=set(d["liked_by"]),
        reports=set(d["reports"]),
        blocked=set(d["blocked"]),
        banned=d["banned"],
        search_pref=Gender(d["search_pref"]) if d["search_pref"] else None,
        photo_file_id=d.get("photo_file_id"),
    )


class Database:
    """In-memory database for the chat bot, mirrored to SQLite."""

    def __init__(self, path: Optional[str] = None):
        self.users: dict[int, UserProfile] = {}
        self.queue: list[int] = []  # user_ids waiting for a partner
        self.processed_charges: set[str] = set()  # Telegram payment charge ids

        # SQLite persistence ("" or None disables it — memory only)
        self.path = os.getenv("DB_PATH", "bot.db") if path is None else path
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        if self.path:
            self._connect()
            self._load()

    # ── Persistence ──────────────────────────────────────────────

    def _connect(self):
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS users "
            "(user_id INTEGER PRIMARY KEY, data TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS queue "
            "(user_id INTEGER PRIMARY KEY, pos INTEGER NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS charges (charge_id TEXT PRIMARY KEY)"
        )
        conn.commit()
        self._conn = conn

    def _load(self):
        with self._lock, self._conn:
            for (data,) in self._conn.execute("SELECT data FROM users"):
                try:
                    user = _user_from_json(data)
                except (KeyError, ValueError, TypeError):
                    continue  # skip a corrupt row instead of crashing the bot
                self.users[user.user_id] = user
            self.queue = [
                uid
                for (uid,) in self._conn.execute(
                    "SELECT user_id FROM queue ORDER BY pos"
                )
                if uid in self.users
            ]
            self.processed_charges = {
                cid for (cid,) in self._conn.execute("SELECT charge_id FROM charges")
            }

    def _save(self):
        """Write the full state atomically. Every mutation path calls this."""
        if not self._conn:
            return
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM users")
            self._conn.executemany(
                "INSERT INTO users(user_id, data) VALUES (?, ?)",
                [(u.user_id, _user_to_json(u)) for u in self.users.values()],
            )
            self._conn.execute("DELETE FROM queue")
            self._conn.executemany(
                "INSERT INTO queue(user_id, pos) VALUES (?, ?)",
                [(uid, pos) for pos, uid in enumerate(self.queue)],
            )
            self._conn.execute("DELETE FROM charges")
            self._conn.executemany(
                "INSERT INTO charges(charge_id) VALUES (?)",
                [(cid,) for cid in self.processed_charges],
            )

    def close(self):
        """Flush and close the SQLite store."""
        try:
            self._save()
        finally:
            if self._conn:
                with self._lock:
                    self._conn.close()
                    self._conn = None

    # ── User management ──────────────────────────────────────────

    def get_user(self, user_id: int) -> Optional[UserProfile]:
        return self.users.get(user_id)

    def register_user(self, user_id: int, username: Optional[str] = None) -> UserProfile:
        if user_id not in self.users:
            self.users[user_id] = UserProfile(user_id=user_id, username=username)
            self._save()
        elif username and self.users[user_id].username != username:
            self.users[user_id].username = username
            self._save()
        return self.users[user_id]

    def update_gender(self, user_id: int, gender: Gender):
        if user_id in self.users:
            self.users[user_id].gender = gender
            self._save()

    def update_country(self, user_id: int, country: str):
        if user_id in self.users:
            self.users[user_id].country = country
            self._save()

    def update_preferred_gender(self, user_id: int, preferred: Gender):
        if user_id in self.users:
            self.users[user_id].preferred_gender = preferred
            self._save()

    def set_photo(self, user_id: int, file_id: str) -> bool:
        """Store the user's profile photo (Telegram file_id)."""
        user = self.users.get(user_id)
        if not user:
            return False
        user.photo_file_id = file_id
        self._save()
        return True

    # ── Coins ─────────────────────────────────────────────────────

    def add_coins(self, user_id: int, amount: int) -> int:
        """Add coins to a user and return the new balance."""
        user = self.users.get(user_id)
        if not user:
            return 0
        user.coins = max(0, user.coins + amount)
        self._save()
        return user.coins

    def spend_coins(self, user_id: int, amount: int) -> bool:
        """Deduct coins if the balance allows it. Returns success."""
        user = self.users.get(user_id)
        if not user or user.coins < amount:
            return False
        user.coins -= amount
        self._save()
        return True

    # ── Referrals ─────────────────────────────────────────────────

    def apply_referral(self, referrer_id: int, new_user_id: int) -> Optional[tuple[int, int]]:
        """
        Credit a referral (once per account).
        Returns (referrer_gain, new_user_gain) or None if not applicable.
        """
        if referrer_id == new_user_id:
            return None
        referrer = self.users.get(referrer_id)
        new_user = self.users.get(new_user_id)
        if not referrer or not new_user or referrer.banned:
            return None
        if new_user.referred_by is not None:
            return None

        new_user.referred_by = referrer_id
        referrer.referral_count += 1
        referrer.referral_earned += REFERRAL_REWARD
        self.add_coins(referrer_id, REFERRAL_REWARD)
        self.add_coins(new_user_id, REFERRED_BONUS)
        self._save()
        return REFERRAL_REWARD, REFERRED_BONUS

    # ── Likes ─────────────────────────────────────────────────────

    def add_like(self, from_id: int, to_id: int) -> tuple[bool, int]:
        """Like a profile. Returns (was_new_like, target_total_likes)."""
        target = self.users.get(to_id)
        if not target or from_id == to_id:
            return False, target.likes if target else 0
        if from_id in target.liked_by:
            return False, target.likes
        target.liked_by.add(from_id)
        target.likes += 1
        self._save()
        return True, target.likes

    def likers_of(self, user_id: int) -> list["UserProfile"]:
        """Return profiles of users who liked this user."""
        user = self.users.get(user_id)
        if not user:
            return []
        return [self.users[uid] for uid in user.liked_by if uid in self.users]

    # ── Reports ───────────────────────────────────────────────────

    def add_report(self, reporter_id: int, target_id: int) -> bool:
        """
        Report a user and block them from matching with the reporter.
        Returns True if this report triggered a ban (threshold reached).
        """
        reporter = self.users.get(reporter_id)
        target = self.users.get(target_id)
        if not reporter or not target or reporter_id == target_id:
            return False

        reporter.blocked.add(target_id)

        if reporter_id in target.reports:
            self._save()
            return False
        target.reports.add(reporter_id)
        self._save()

        if not target.banned and len(target.reports) >= BAN_REPORT_THRESHOLD:
            target.banned = True
            self._save()
            return True
        return False

    # ── Queue / matchmaking ──────────────────────────────────────

    def add_to_queue(self, user_id: int, search_pref: Optional[Gender] = None):
        user = self.users.get(user_id)
        if user and user_id not in self.queue and not user.banned:
            user.state = ChatState.SEARCHING
            user.search_pref = search_pref
            self.queue.append(user_id)
            self._save()

    def remove_from_queue(self, user_id: int):
        changed = user_id in self.queue
        if changed:
            self.queue.remove(user_id)
        user = self.users.get(user_id)
        if not user:
            if changed:
                self._save()
            return
        if user.state == ChatState.SEARCHING:
            user.state = ChatState.IDLE
            changed = True
        if user.search_pref is not None:
            user.search_pref = None
            changed = True
        if changed:
            self._save()

    def find_match(self, user_id: int) -> Optional[int]:
        """
        Find a compatible partner from the queue.
        Rules:
          • Prefer different country (cross-border chat)
          • Respect the active search filter of both users
          • Skip banned users and mutually blocked pairs
          • Never match with self
        """
        user = self.users.get(user_id)
        if not user or user.banned:
            return None

        best_match: Optional[int] = None
        best_is_cross_country = False

        for candidate_id in self.queue:
            if candidate_id == user_id:
                continue
            candidate = self.users.get(candidate_id)
            if not candidate or candidate.banned:
                continue
            if candidate_id in user.blocked or user_id in candidate.blocked:
                continue

            # Check gender preferences (bidirectional)
            if not self._gender_compatible(user, candidate):
                continue

            is_cross = (
                user.country and candidate.country
                and user.country.lower() != candidate.country.lower()
            )

            # Prefer cross-country matches
            if best_match is None or (is_cross and not best_is_cross_country):
                best_match = candidate_id
                best_is_cross_country = is_cross

        return best_match

    @staticmethod
    def _effective_pref(user: UserProfile) -> Gender:
        """Active per-search filter, falling back to the saved preference."""
        return user.search_pref if user.search_pref is not None else user.preferred_gender

    def _gender_compatible(self, a: UserProfile, b: UserProfile) -> bool:
        """Check if two users' active search filters are mutually compatible."""
        a_want = self._effective_pref(a)
        b_want = self._effective_pref(b)
        a_ok = a_want == Gender.ANY or a_want == b.gender
        b_ok = b_want == Gender.ANY or b_want == a.gender
        return a_ok and b_ok

    # ── Chat session management ──────────────────────────────────

    def pair_users(self, user_a: int, user_b: int):
        for uid in (user_a, user_b):
            self.remove_from_queue(uid)
            user = self.users[uid]
            user.state = ChatState.CHATTING
            user.total_chats += 1

        self.users[user_a].partner_id = user_b
        self.users[user_b].partner_id = user_a
        self._save()

    def end_chat(self, user_id: int) -> Optional[int]:
        """End the chat for user_id and return the partner's id."""
        user = self.users.get(user_id)
        if not user or user.state != ChatState.CHATTING:
            return None

        partner_id = user.partner_id
        user.state = ChatState.IDLE
        user.partner_id = None
        user.search_pref = None

        if partner_id and partner_id in self.users:
            partner = self.users[partner_id]
            partner.state = ChatState.IDLE
            partner.partner_id = None
            partner.search_pref = None

        self._save()
        return partner_id

    # ── Stats ────────────────────────────────────────────────────

    @property
    def online_count(self) -> int:
        return len(self.users)

    @property
    def searching_count(self) -> int:
        return len(self.queue)

    @property
    def chatting_count(self) -> int:
        return sum(1 for u in self.users.values() if u.state == ChatState.CHATTING) // 2


# Singleton instance (mirrored to DB_PATH, default ./bot.db)
db = Database()
atexit.register(db.close)
