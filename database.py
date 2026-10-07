"""
Telegram Random Chat Bot — Database & User Models

Uses an in-memory store (easily swappable for SQLite/Redis in production).
Tracks user profiles, active sessions, and the matchmaking queue.
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import time


class Gender(Enum):
    MALE = "male"
    FEMALE = "female"
    ANY = "any"  # preference: match with anyone


class ChatState(Enum):
    IDLE = "idle"              # registered but not searching
    SEARCHING = "searching"    # in the matchmaking queue
    CHATTING = "chatting"      # actively paired with someone


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


class Database:
    """In-memory database for the chat bot."""

    def __init__(self):
        self.users: dict[int, UserProfile] = {}
        self.queue: list[int] = []  # user_ids waiting for a partner

    # ── User management ──────────────────────────────────────────

    def get_user(self, user_id: int) -> Optional[UserProfile]:
        return self.users.get(user_id)

    def register_user(self, user_id: int, username: Optional[str] = None) -> UserProfile:
        if user_id not in self.users:
            self.users[user_id] = UserProfile(user_id=user_id, username=username)
        return self.users[user_id]

    def update_gender(self, user_id: int, gender: Gender):
        if user_id in self.users:
            self.users[user_id].gender = gender

    def update_country(self, user_id: int, country: str):
        if user_id in self.users:
            self.users[user_id].country = country

    def update_preferred_gender(self, user_id: int, preferred: Gender):
        if user_id in self.users:
            self.users[user_id].preferred_gender = preferred

    # ── Queue / matchmaking ──────────────────────────────────────

    def add_to_queue(self, user_id: int):
        user = self.users.get(user_id)
        if user and user_id not in self.queue:
            user.state = ChatState.SEARCHING
            self.queue.append(user_id)

    def remove_from_queue(self, user_id: int):
        if user_id in self.queue:
            self.queue.remove(user_id)
        user = self.users.get(user_id)
        if user and user.state == ChatState.SEARCHING:
            user.state = ChatState.IDLE

    def find_match(self, user_id: int) -> Optional[int]:
        """
        Find a compatible partner from the queue.
        Rules:
          • Prefer different country (cross-border chat)
          • Respect gender preferences
          • Never match with self
        """
        user = self.users.get(user_id)
        if not user:
            return None

        best_match: Optional[int] = None
        best_is_cross_country = False

        for candidate_id in self.queue:
            if candidate_id == user_id:
                continue
            candidate = self.users.get(candidate_id)
            if not candidate:
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

    def _gender_compatible(self, a: UserProfile, b: UserProfile) -> bool:
        """Check if two users' gender preferences are mutually compatible."""
        a_ok = a.preferred_gender == Gender.ANY or a.preferred_gender == b.gender
        b_ok = b.preferred_gender == Gender.ANY or b.preferred_gender == a.gender
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

    def end_chat(self, user_id: int) -> Optional[int]:
        """End the chat for user_id and return the partner's id."""
        user = self.users.get(user_id)
        if not user or user.state != ChatState.CHATTING:
            return None

        partner_id = user.partner_id
        user.state = ChatState.IDLE
        user.partner_id = None

        if partner_id and partner_id in self.users:
            partner = self.users[partner_id]
            partner.state = ChatState.IDLE
            partner.partner_id = None

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


# Singleton instance
db = Database()
