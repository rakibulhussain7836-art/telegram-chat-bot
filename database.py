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
import hashlib
import json
import math
import os
import random
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
CHAT_REQUEST_COST = 1      # coins to send a chat request from Nearby / by ID
DIRECT_MESSAGE_COST = 1    # coins to start a Direct Message from a profile card
CHAT_REQUEST_TTL = 120     # seconds the receiver has to answer a request
NEARBY_RADIUS_KM = 50      # default radius for the Nearby search
EARTH_RADIUS_KM = 6371.0
VIEW_ALERT_COOLDOWN = 600  # seconds between "someone viewed you" toasts
BROWSE_PAGE_SIZE = 5       # profiles per page in the Browse People list
RECENT_PARTNER_LIMIT = 20  # chat partners remembered per user
DAILY_REWARD_COINS = 1     # coins per match (MeChat-style free coin)
DAILY_REWARD_MAX = 10      # matches rewarded per day
DM_TTL = 7 * 86400         # unread direct messages kept for 7 days

# ── Short public-ID slugs (display: /user_xxx, base36) ───────────
_B36_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"


def _to_b36(n: int) -> str:
    if n <= 0:
        return "0"
    out = []
    while n:
        n, rem = divmod(n, 36)
        out.append(_B36_DIGITS[rem])
    return "".join(reversed(out))


def _from_b36(s: str) -> Optional[int]:
    try:
        return int(s, 36)
    except (TypeError, ValueError):
        return None


def public_id_slug(user: "UserProfile") -> str:
    """Shareable ID without the leading slash, safe for deep links: user_r3u2."""
    return f"user_{_to_b36(user.public_id)}"


def format_public_id(user: "UserProfile") -> str:
    """Human-shareable ID, e.g. /user_r3u2 (same style as the reference bot)."""
    return f"/{public_id_slug(user)}"


@dataclass
class UserProfile:
    user_id: int
    username: Optional[str] = None
    # ── Public card fields (shown on profile cards) ──
    name: Optional[str] = None
    age: Optional[int] = None
    city: Optional[str] = None
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
    # ── Discovery: short shareable ID, location, contacts ──
    public_id: int = 0
    lat: Optional[float] = None
    lon: Optional[float] = None
    contacts: set[int] = field(default_factory=set)
    # ── Verification (admin reviews a photo evidence) ──
    verified: bool = False
    verified_gender: Optional[Gender] = None
    # ── VIP & notifications ──
    vip: bool = False
    notify_on_end: bool = False      # 🔔 ping me when my chat ends
    view_alert_at: float = 0.0       # last "someone viewed you" toast
    # ── Chat history (most recent partners, newest first) ──
    recent_partners: list[int] = field(default_factory=list)
    # ── Daily match reward (1 coin per match, capped per day) ──
    reward_date: str = ""
    reward_count: int = 0


def _user_to_json(user: UserProfile) -> str:
    """Serialize a profile for the SQLite store."""
    return json.dumps(
        {
            "user_id": user.user_id,
            "username": user.username,
            "name": user.name,
            "age": user.age,
            "city": user.city,
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
            "public_id": user.public_id,
            "lat": user.lat,
            "lon": user.lon,
            "contacts": sorted(user.contacts),
            "verified": user.verified,
            "verified_gender": (
                user.verified_gender.value if user.verified_gender else None
            ),
            "vip": user.vip,
            "notify_on_end": user.notify_on_end,
            "view_alert_at": user.view_alert_at,
            "recent_partners": list(user.recent_partners),
            "reward_date": user.reward_date,
            "reward_count": user.reward_count,
        }
    )


def _enum_or_none(enum_cls, value, default=None):
    """Parse an enum value; missing/renamed values fall back to `default`."""
    if value is None:
        return default
    try:
        return enum_cls(value)
    except ValueError:
        return default


def _user_from_json(data: str) -> UserProfile:
    """Deserialize a profile.

    Every field except user_id is OPTIONAL: rows written by older bot
    versions keep loading after an upgrade (new fields simply get their
    defaults), so users never have to redo name/gender/age onboarding
    when a new version is deployed.
    """
    d = json.loads(data)
    return UserProfile(
        user_id=d["user_id"],
        username=d.get("username"),
        name=d.get("name"),
        age=d.get("age"),
        city=d.get("city"),
        gender=_enum_or_none(Gender, d.get("gender")),
        country=d.get("country"),
        preferred_gender=_enum_or_none(
            Gender, d.get("preferred_gender"), Gender.ANY
        ),
        state=_enum_or_none(ChatState, d.get("state"), ChatState.IDLE),
        partner_id=d.get("partner_id"),
        registered_at=d.get("registered_at") or time.time(),
        total_chats=d.get("total_chats", 0),
        coins=d.get("coins", STARTING_COINS),
        referral_count=d.get("referral_count", 0),
        referral_earned=d.get("referral_earned", 0),
        referred_by=d.get("referred_by"),
        likes=d.get("likes", 0),
        liked_by=set(d.get("liked_by") or []),
        reports=set(d.get("reports") or []),
        blocked=set(d.get("blocked") or []),
        banned=bool(d.get("banned", False)),
        search_pref=_enum_or_none(Gender, d.get("search_pref")),
        photo_file_id=d.get("photo_file_id"),
        public_id=d.get("public_id", 0),
        lat=d.get("lat"),
        lon=d.get("lon"),
        contacts=set(d.get("contacts") or []),
        verified=bool(d.get("verified", False)),
        verified_gender=_enum_or_none(Gender, d.get("verified_gender")),
        vip=bool(d.get("vip", False)),
        notify_on_end=bool(d.get("notify_on_end", False)),
        view_alert_at=d.get("view_alert_at", 0.0),
        recent_partners=list(d.get("recent_partners") or []),
        reward_date=d.get("reward_date", ""),
        reward_count=d.get("reward_count", 0),
    )


class Database:
    """In-memory database for the chat bot, mirrored to SQLite."""

    def __init__(self, path: Optional[str] = None):
        self.users: dict[int, UserProfile] = {}
        self.queue: list[int] = []  # user_ids waiting for a partner
        self.processed_charges: set[str] = set()  # Telegram payment charge ids
        # Chat requests: "from_id:to_id" -> {"status": pending/accepted/declined}
        self.requests: dict[str, dict] = {}
        # Photo evidence waiting for admin review: user_id -> {gender, file_id}
        self.pending_verifications: dict[int, dict] = {}
        # Unread direct messages: to_id -> {from_id, text, at}
        self.pending_dms: dict[int, dict] = {}
        # O(1) public-ID lookup index (public_id -> user_id)
        self._by_public_id: dict[int, int] = {}

        # SQLite persistence ("" or None disables it — memory only)
        self.path = os.getenv("DB_PATH", "bot.db") if path is None else path
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        if self.path:
            self._connect()
            self._load()

    # ── Persistence ──────────────────────────────────────────────

    def _connect(self):
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
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
        conn.execute(
            "CREATE TABLE IF NOT EXISTS state "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
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
            state = {
                key: value
                for key, value in self._conn.execute("SELECT key, value FROM state")
            }
        try:
            self.requests = json.loads(state.get("requests", "{}"))
        except ValueError:
            self.requests = {}
        try:
            self.pending_verifications = {
                int(k): v
                for k, v in json.loads(state.get("verifications", "{}")).items()
            }
        except ValueError:
            self.pending_verifications = {}
        try:
            self.pending_dms = {
                int(k): v
                for k, v in json.loads(state.get("dms", "{}")).items()
            }
        except ValueError:
            self.pending_dms = {}
        # Older accounts (created before public IDs existed) get one now.
        assigned = False
        self._by_public_id.clear()
        for user in self.users.values():
            if user.public_id:
                self._by_public_id[user.public_id] = user.user_id
            else:
                user.public_id = self._next_public_id()
                self._by_public_id[user.public_id] = user.user_id
                assigned = True
        if assigned:
            self._save()

    def _save(self):
        """Full state snapshot — only used on close. Mutations write single rows."""
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
            for key, value in (
                ("requests", json.dumps(self.requests)),
                ("verifications", json.dumps(self.pending_verifications)),
                ("dms", json.dumps(self.pending_dms)),
            ):
                self._conn.execute(
                    "INSERT INTO state(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )

    # ── Targeted writes (O(1) per mutation, not a full dump) ─────

    def _write_user(self, user: Optional[UserProfile]):
        if not user or not self._conn:
            return
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO users(user_id, data) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET data = excluded.data",
                (user.user_id, _user_to_json(user)),
            )

    def _write_users(self, *users: Optional[UserProfile]):
        rows = [(u.user_id, _user_to_json(u)) for u in users if u]
        if not rows or not self._conn:
            return
        with self._lock, self._conn:
            self._conn.executemany(
                "INSERT INTO users(user_id, data) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET data = excluded.data",
                rows,
            )

    def _write_queue_entry(self, user_id: int, pos: int):
        if not self._conn:
            return
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO queue(user_id, pos) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET pos = excluded.pos",
                (user_id, pos),
            )

    def _delete_queue_entry(self, user_id: int):
        if not self._conn:
            return
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM queue WHERE user_id = ?", (user_id,))

    def _write_charge(self, charge_id: str):
        if not self._conn:
            return
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO charges(charge_id) VALUES (?)", (charge_id,)
            )

    def _write_state(self, key: str, value: str):
        if not self._conn:
            return
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO state(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def _write_requests(self):
        self._write_state("requests", json.dumps(self.requests))

    def _write_verifications(self):
        self._write_state("verifications", json.dumps(self.pending_verifications))

    def _write_dms(self):
        self._write_state("dms", json.dumps(self.pending_dms))

    def flush(self):
        """Persist the full snapshot right now (used before a backup upload)."""
        self._save()
        self._checkpoint()

    def _checkpoint(self):
        """Merge the WAL into the main DB file so a plain file copy is complete."""
        if not self._conn:
            return
        with self._lock:
            try:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.Error:
                pass  # backup still works, worst case the next checkpoint catches up

    def snapshot_hash(self) -> str:
        """Stable hash of the logical contents — used by the backup loop to
        upload only when the database actually changed since the last backup."""
        with self._lock:
            payload = json.dumps(
                {
                    "users": [
                        (u.user_id, _user_to_json(u))
                        for u in sorted(
                            self.users.values(), key=lambda u: u.user_id
                        )
                    ],
                    "queue": list(self.queue),
                    "charges": sorted(self.processed_charges),
                    "requests": self.requests,
                    "verifications": self.pending_verifications,
                    "dms": self.pending_dms,
                },
                sort_keys=True,
            )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def reload(self):
        """Drop all in-memory state and re-read the SQLite file.

        Used after an external restore of the DB file (e.g. downloading a
        backup from the backup Telegram channel on a fresh deploy).
        """
        if not self.path:
            return
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None
        self.users.clear()
        self.queue.clear()
        self.processed_charges.clear()
        self.requests.clear()
        self.pending_verifications.clear()
        self.pending_dms.clear()
        self._by_public_id.clear()
        self._connect()
        self._load()

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

    def register_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        name: Optional[str] = None,
    ) -> UserProfile:
        if user_id not in self.users:
            user = UserProfile(user_id=user_id, username=username, name=name)
            user.public_id = self._next_public_id()
            self.users[user_id] = user
            self._by_public_id[user.public_id] = user_id
            self._write_user(user)
        else:
            user = self.users[user_id]
            changed = False
            if username and user.username != username:
                user.username = username
                changed = True
            if name and not user.name:
                user.name = name
                changed = True
            if changed:
                self._write_user(user)
        return self.users[user_id]

    def _next_public_id(self) -> int:
        """Short 6-digit ID other people can use to find this account."""
        while True:
            candidate = random.randint(100000, 999999)
            if candidate not in self._by_public_id:
                return candidate

    def find_by_public_id(self, public_id: int) -> Optional["UserProfile"]:
        uid = self._by_public_id.get(public_id)
        if uid is not None:
            user = self.users.get(uid)
            if user is not None and user.public_id == public_id:
                return user
            self._by_public_id.pop(public_id, None)  # stale index entry
        for user in self.users.values():
            if user.public_id == public_id:
                self._by_public_id[public_id] = user.user_id
                return user
        return None

    def resolve_id(self, value) -> Optional["UserProfile"]:
        """Accept a public ID (int or /user_xxx slug) or a Telegram user ID."""
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("/"):
                value = value[1:]
            if value.lower().startswith("user_"):
                number = _from_b36(value[5:])
                if number is None:
                    return None
                return self.find_by_public_id(number)
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return self.users.get(number) or self.find_by_public_id(number)

    def update_gender(self, user_id: int, gender: Gender):
        if user_id in self.users:
            self.users[user_id].gender = gender
            self._write_user(self.users[user_id])

    def update_country(self, user_id: int, country: str):
        if user_id in self.users:
            self.users[user_id].country = country
            self._write_user(self.users[user_id])

    def update_preferred_gender(self, user_id: int, preferred: Gender):
        if user_id in self.users:
            self.users[user_id].preferred_gender = preferred
            self._write_user(self.users[user_id])

    def update_name(self, user_id: int, name: str) -> bool:
        user = self.users.get(user_id)
        if not user:
            return False
        user.name = name.strip()[:50] or user.name
        self._write_user(user)
        return True

    def update_age(self, user_id: int, age: int) -> bool:
        user = self.users.get(user_id)
        if not user:
            return False
        user.age = age
        self._write_user(user)
        return True

    def update_city(self, user_id: int, city: str) -> bool:
        user = self.users.get(user_id)
        if not user:
            return False
        user.city = city.strip()[:50] or user.city
        self._write_user(user)
        return True

    # ── VIP / chat-end notifications ─────────────────────────────

    def set_vip(self, user_id: int, value: bool = True) -> bool:
        user = self.users.get(user_id)
        if not user:
            return False
        user.vip = value
        self._write_user(user)
        return True

    def set_notify_end(self, user_id: int, value: bool) -> bool:
        user = self.users.get(user_id)
        if not user:
            return False
        user.notify_on_end = value
        self._write_user(user)
        return True

    # ── Profile views ────────────────────────────────────────────

    def record_view(self, viewer_id: int, target_id: int) -> bool:
        """
        Someone opened a profile card. Returns True when the owner should
        get a "someone viewed your profile" toast (cooldown-limited).
        """
        viewer = self.users.get(viewer_id)
        target = self.users.get(target_id)
        if not viewer or not target or viewer_id == target_id:
            return False
        now = time.time()
        if now - target.view_alert_at < VIEW_ALERT_COOLDOWN:
            return False
        target.view_alert_at = now
        self._write_user(target)
        return True

    def block_user(self, user_id: int, target_id: int) -> bool:
        """Block someone: never match with them again and drop them from contacts."""
        me = self.users.get(user_id)
        if not me or user_id == target_id or target_id not in self.users:
            return False
        me.blocked.add(target_id)
        me.contacts.discard(target_id)
        self._write_user(me)
        return True

    def unblock_user(self, user_id: int, target_id: int) -> bool:
        """Undo a block (they become matchable again)."""
        me = self.users.get(user_id)
        if not me or target_id not in me.blocked:
            return False
        me.blocked.discard(target_id)
        self._write_user(me)
        return True

    def browse_users(
        self,
        user_id: int,
        offset: int = 0,
        limit: int = BROWSE_PAGE_SIZE,
    ) -> tuple[list["UserProfile"], int]:
        """Everyone except me, page by page — powers 🎉 Browse People."""
        return self.browse_filtered(user_id, "all", offset, limit)

    def browse_filtered(
        self,
        user_id: int,
        kind: str = "all",
        offset: int = 0,
        limit: int = BROWSE_PAGE_SIZE,
    ) -> tuple[list["UserProfile"], int]:
        """
        Browse categories (MeChat-style "Who do you want to see?"):
          all     — everyone except me
          myage   — people within ±2 years of my age
          ready   — complete profiles, not banned, not busy
          new     — joined in the last 7 days
          recent  — people I recently chatted with
          popular — most liked first
        """
        me = self.users.get(user_id)
        now = time.time()

        if kind == "recent":
            found = [
                self.users[uid]
                for uid in (me.recent_partners if me else [])
                if uid in self.users and not self.users[uid].banned
            ]
            return found[offset : offset + limit], len(found)

        found = [
            u
            for u in self.users.values()
            if u.user_id != user_id and not u.banned
        ]

        if kind == "myage" and me and me.age:
            found = [u for u in found if u.age and abs(u.age - me.age) <= 2]
            found.sort(key=lambda u: abs((u.age or 0) - me.age))
        elif kind == "ready":
            found = [
                u
                for u in found
                if u.gender and u.country and u.state != ChatState.CHATTING
            ]
            found.sort(key=lambda u: u.state == ChatState.SEARCHING, reverse=True)
        elif kind == "new":
            found = [u for u in found if now - u.registered_at <= 7 * 86400]
            found.sort(key=lambda u: u.registered_at, reverse=True)
        elif kind == "popular":
            found.sort(key=lambda u: u.likes, reverse=True)
        else:  # "all"
            found.sort(key=lambda u: u.registered_at, reverse=True)

        return found[offset : offset + limit], len(found)

    def blocked_of(self, user_id: int) -> list["UserProfile"]:
        """Profiles I've blocked/reported (for the 🚫 Blocked Users list)."""
        me = self.users.get(user_id)
        if not me:
            return []
        return [
            self.users[uid] for uid in sorted(me.blocked) if uid in self.users
        ]

    def set_photo(self, user_id: int, file_id: str) -> bool:
        """Store the user's profile photo (Telegram file_id)."""
        user = self.users.get(user_id)
        if not user:
            return False
        user.photo_file_id = file_id
        self._write_user(user)
        return True

    # ── Location / Nearby ────────────────────────────────────────

    def set_location(self, user_id: int, lat: float, lon: float) -> bool:
        user = self.users.get(user_id)
        if not user:
            return False
        user.lat, user.lon = lat, lon
        self._write_user(user)
        return True

    def has_location(self, user_id: int) -> bool:
        user = self.users.get(user_id)
        return bool(user and user.lat is not None and user.lon is not None)

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Great-circle distance between two coordinates, in kilometres."""
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = (
            math.sin(dphi / 2) ** 2
            + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
        )
        return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))

    def distance_km(self, a_id: int, b_id: int) -> Optional[float]:
        a, b = self.users.get(a_id), self.users.get(b_id)
        if not a or not b or a.lat is None or b.lat is None:
            return None
        return self._haversine(a.lat, a.lon, b.lat, b.lon)

    def nearby_users(
        self,
        user_id: int,
        radius_km: float = NEARBY_RADIUS_KM,
        limit: int = 20,
    ) -> list[tuple["UserProfile", float]]:
        """Users with a shared location inside the radius, nearest first."""
        me = self.users.get(user_id)
        if not me or me.lat is None:
            return []
        found = []
        for user in self.users.values():
            if user.user_id == user_id or user.banned or user.lat is None:
                continue
            dist = self._haversine(me.lat, me.lon, user.lat, user.lon)
            if dist <= radius_km:
                found.append((user, dist))
        found.sort(key=lambda pair: pair[1])
        return found[:limit]

    # ── Contacts (added manually while chatting) ─────────────────

    def add_contact(self, user_id: int, contact_id: int) -> bool:
        """Add someone to my contact list (only from an active chat)."""
        me = self.users.get(user_id)
        target = self.users.get(contact_id)
        if not me or not target or user_id == contact_id:
            return False
        if contact_id in me.contacts:
            return False
        me.contacts.add(contact_id)
        self._write_user(me)
        return True

    def remove_contact(self, user_id: int, contact_id: int) -> bool:
        me = self.users.get(user_id)
        if not me or contact_id not in me.contacts:
            return False
        me.contacts.remove(contact_id)
        self._write_user(me)
        return True

    def contacts_of(self, user_id: int) -> list["UserProfile"]:
        user = self.users.get(user_id)
        if not user:
            return []
        return [
            self.users[uid] for uid in sorted(user.contacts) if uid in self.users
        ]

    # ── Direct messages (privacy: content hidden until opened) ───

    def queue_dm(self, to_id: int, from_id: int, text: str) -> bool:
        """Store an unread DM. The receiver sees it only via pop_dm()."""
        if to_id not in self.users or from_id not in self.users:
            return False
        self.pending_dms[to_id] = {
            "from_id": from_id,
            "text": text[:1000],
            "at": time.time(),
        }
        self._write_dms()
        return True

    def pop_dm(self, to_id: int) -> Optional[dict]:
        """Take the oldest unread DM (expired ones are dropped silently)."""
        dm = self.pending_dms.get(to_id)
        if not dm:
            return None
        if time.time() - dm.get("at", 0) > DM_TTL:
            del self.pending_dms[to_id]
            self._write_dms()
            return None
        del self.pending_dms[to_id]
        self._write_dms()
        return dm

    # ── Chat requests (cost CHAT_REQUEST_COST coins) ─────────────

    @staticmethod
    def _request_key(from_id: int, to_id: int) -> str:
        return f"{from_id}:{to_id}"

    def _expire_if_stale(self, from_id: int, to_id: int) -> bool:
        """Refund and drop a request the receiver never answered in time."""
        key = self._request_key(from_id, to_id)
        req = self.requests.get(key)
        if not req or req.get("status") != "pending":
            return False
        if time.time() - req.get("created_at", 0) <= CHAT_REQUEST_TTL:
            return False
        req["status"] = "expired"
        self.add_coins(from_id, CHAT_REQUEST_COST)  # never burn coins silently
        self._write_requests()
        return True

    def request_status(self, from_id: int, to_id: int) -> Optional[str]:
        self._expire_if_stale(from_id, to_id)
        req = self.requests.get(self._request_key(from_id, to_id))
        return req["status"] if req else None

    def create_request(self, from_id: int, to_id: int) -> tuple[bool, str]:
        """
        Send a chat request (charges CHAT_REQUEST_COST coins).
        Returns (ok, reason) — reason is used directly in bot replies.
        """
        sender = self.users.get(from_id)
        target = self.users.get(to_id)
        if not sender or not target:
            return False, "That user no longer exists."
        if from_id == to_id:
            return False, "You can't send a request to yourself."
        if sender.banned or target.banned:
            return False, "🚫 Your account is restricted."
        if self.request_status(from_id, to_id) == "pending":
            return False, "You already have a pending request for this person."
        if self.request_status(to_id, from_id) == "pending":
            return False, "They already sent you a request — accept it instead."
        if not self.spend_coins(from_id, CHAT_REQUEST_COST):
            return False, (
                f"Not enough Coins! A chat request costs "
                f"{CHAT_REQUEST_COST} 🪙."
            )
        self.requests[self._request_key(from_id, to_id)] = {
            "status": "pending",
            "created_at": time.time(),
        }
        self._write_requests()
        return True, "ok"

    def resolve_request(self, from_id: int, to_id: int, accepted: bool) -> bool:
        """Mark a pending request accepted/declined. Returns False if missing."""
        self._expire_if_stale(from_id, to_id)
        key = self._request_key(from_id, to_id)
        req = self.requests.get(key)
        if not req or req.get("status") != "pending":
            return False
        req["status"] = "accepted" if accepted else "declined"
        self._write_requests()
        return True

    def cancel_request(self, from_id: int, to_id: int) -> bool:
        """Drop a still-pending request (e.g. it could not be delivered)."""
        key = self._request_key(from_id, to_id)
        req = self.requests.get(key)
        if not req or req.get("status") != "pending":
            return False
        del self.requests[key]
        self._write_requests()
        return True

    # ── Verification (photo evidence reviewed by the admin) ──────

    def queue_verification(self, user_id: int, gender: Gender, file_id: str) -> bool:
        user = self.users.get(user_id)
        if not user or user.verified:
            return False
        self.pending_verifications[user_id] = {
            "gender": gender.value,
            "file_id": file_id,
            "created_at": time.time(),
        }
        self._write_verifications()
        return True

    def pending_verifications_list(self) -> list[tuple[int, dict]]:
        return sorted(self.pending_verifications.items())

    def approve_verification(self, user_id: int) -> Optional["UserProfile"]:
        """Approve the pending request. Returns the user, or None if nothing pending."""
        pending = self.pending_verifications.pop(user_id, None)
        user = self.users.get(user_id)
        if not pending or not user:
            return None
        user.verified = True
        user.verified_gender = Gender(pending["gender"])
        self._write_users(user)
        self._write_verifications()
        return user

    def reject_verification(self, user_id: int) -> bool:
        if user_id not in self.pending_verifications:
            return False
        del self.pending_verifications[user_id]
        self._write_verifications()
        return True

    # ── Coins ─────────────────────────────────────────────────────

    def add_coins(self, user_id: int, amount: int) -> int:
        """Add coins to a user and return the new balance."""
        user = self.users.get(user_id)
        if not user:
            return 0
        user.coins = max(0, user.coins + amount)
        self._write_user(user)
        return user.coins

    def spend_coins(self, user_id: int, amount: int) -> bool:
        """Deduct coins if the balance allows it. Returns success."""
        user = self.users.get(user_id)
        if not user or user.coins < amount:
            return False
        user.coins -= amount
        self._write_user(user)
        return True

    def add_charge(self, charge_id: str) -> bool:
        """Record a processed Telegram payment. Returns False if already seen."""
        if charge_id in self.processed_charges:
            return False
        self.processed_charges.add(charge_id)
        self._write_charge(charge_id)
        return True

    def award_match_reward(self, user_id: int) -> int:
        """
        MeChat-style free coin — girls only: +DAILY_REWARD_COINS per match,
        up to DAILY_REWARD_MAX matches per day. Boys never get the reward.
        """
        user = self.users.get(user_id)
        if not user or user.gender != Gender.FEMALE:
            return 0
        today = time.strftime("%Y-%m-%d")
        if user.reward_date != today:
            user.reward_date = today
            user.reward_count = 0
        if user.reward_count >= DAILY_REWARD_MAX:
            return 0
        user.reward_count += 1
        user.coins = max(0, user.coins + DAILY_REWARD_COINS)
        self._write_user(user)
        return DAILY_REWARD_COINS

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
        referrer.coins = max(0, referrer.coins + REFERRAL_REWARD)
        new_user.coins = max(0, new_user.coins + REFERRED_BONUS)
        self._write_users(referrer, new_user)
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
        self._write_user(target)
        return True, target.likes

    def unlike(self, from_id: int, to_id: int) -> tuple[bool, int]:
        """Remove my like from a profile. Returns (was_removed, new_total)."""
        target = self.users.get(to_id)
        if not target or from_id not in target.liked_by:
            return False, target.likes if target else 0
        target.liked_by.discard(from_id)
        target.likes = max(0, target.likes - 1)
        self._write_user(target)
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
        self._write_user(reporter)

        if reporter_id in target.reports:
            return False
        target.reports.add(reporter_id)

        banned = False
        if not target.banned and len(target.reports) >= BAN_REPORT_THRESHOLD:
            target.banned = True
            banned = True
        self._write_user(target)
        return banned

    # ── Queue / matchmaking ──────────────────────────────────────

    def add_to_queue(self, user_id: int, search_pref: Optional[Gender] = None):
        user = self.users.get(user_id)
        if user and user_id not in self.queue and not user.banned:
            user.state = ChatState.SEARCHING
            user.search_pref = search_pref
            self.queue.append(user_id)
            self._write_user(user)
            self._write_queue_entry(user_id, len(self.queue) - 1)

    def remove_from_queue(self, user_id: int):
        changed = user_id in self.queue
        if changed:
            self.queue.remove(user_id)
            self._delete_queue_entry(user_id)
        user = self.users.get(user_id)
        if not user:
            return
        if user.state == ChatState.SEARCHING:
            user.state = ChatState.IDLE
            changed = True
        if user.search_pref is not None:
            user.search_pref = None
            changed = True
        if changed:
            self._write_user(user)

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
            if uid in self.queue:
                self.queue.remove(uid)
                self._delete_queue_entry(uid)
            user = self.users[uid]
            user.state = ChatState.CHATTING
            user.search_pref = None
            user.total_chats += 1

        # Remember each other in chat history (newest first, capped)
        a, b = self.users[user_a], self.users[user_b]
        a.recent_partners = [user_b] + [
            uid for uid in a.recent_partners if uid != user_b
        ][: RECENT_PARTNER_LIMIT - 1]
        b.recent_partners = [user_a] + [
            uid for uid in b.recent_partners if uid != user_a
        ][: RECENT_PARTNER_LIMIT - 1]

        a.partner_id = user_b
        b.partner_id = user_a
        self._write_users(a, b)

    def end_chat(self, user_id: int) -> Optional[int]:
        """End the chat for user_id and return the partner's id."""
        user = self.users.get(user_id)
        if not user or user.state != ChatState.CHATTING:
            return None

        partner_id = user.partner_id
        user.state = ChatState.IDLE
        user.partner_id = None
        user.search_pref = None
        changed: list[UserProfile] = [user]

        if partner_id and partner_id in self.users:
            partner = self.users[partner_id]
            partner.state = ChatState.IDLE
            partner.partner_id = None
            partner.search_pref = None
            changed.append(partner)

        self._write_users(*changed)
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
