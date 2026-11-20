"""Persistent clans and chat for enrolled Acies guests."""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

MAX_MEMBERS = 30
HISTORY_LIMIT = 50
CLAN_CREATION_FEE = 5_000


@dataclass(frozen=True)
class ChatMessage:
    user_id: int
    name: str
    text: str
    time: int


class SocialStore:
    def __init__(self, path: Path, names: dict[int, str], deck: dict) -> None:
        self.names = names
        self.deck = deck
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS clan (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner INTEGER NOT NULL,
                name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                description TEXT NOT NULL,
                country INTEGER NOT NULL,
                notice TEXT NOT NULL DEFAULT '',
                updated INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS membership (
                user_id INTEGER PRIMARY KEY,
                clan_id INTEGER NOT NULL REFERENCES clan(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS clan_spending (
                user_id INTEGER PRIMARY KEY,
                gold INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chat (
                id INTEGER PRIMARY KEY,
                clan_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                text TEXT NOT NULL,
                time INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS chat_by_clan ON chat(clan_id, id);
        """)

    def clan_id(self, user_id: int) -> int:
        with self.lock:
            member = self.db.execute("SELECT clan_id FROM membership WHERE user_id = ?", (user_id,)).fetchone()
            return member["clan_id"] if member else 0

    def profile(self, clan_id: int) -> dict | None:
        with self.lock:
            clan = self.db.execute("SELECT * FROM clan WHERE id = ?", (clan_id,)).fetchone()
            if clan is None:
                return None
            members = []
            for (user_id,) in self.db.execute("SELECT user_id FROM membership WHERE clan_id = ? ORDER BY user_id", (clan_id,)):
                members.append({
                    "userId": user_id, "name": self.names.get(user_id, "Guest"), "country": 0,
                    "decorations": [0, 0, 0, 0], "pictureUrl": "", "level": 1,
                    "recordPrivate": {}, "recordTeam": {}, "memberAuth": 3 if user_id == clan["owner"] else 0,
                    "point": 0, "card": 0, "weeklyPoint": 0, "weeklyCard": 0,
                    "weeklyCollectionPlay": 0, "lastLoginTime": 0,
                })
            return {
                "clanId": clan_id, "name": clan["name"], "description": clan["description"],
                "country": clan["country"], "decorations": [0, 65536, -1],
                "point": 0, "score": 0, "pointRanking": 0, "scoreRanking": 0, "division": 0,
                "memberCount": len(members), "maxMemberCount": MAX_MEMBERS, "joinScore": 0, "openType": 0,
                "notice": clan["notice"], "updateTime": clan["updated"], "members": members,
                "arena": {
                    "allCards": [{"cardId": card, "count": 1} for card in self.deck["cards"]],
                    "allRunes": [], "rewards": [], "deck": self.deck,
                },
                "allDecorations": [], "posts": [],
            }

    def search(self, keyword: str = "") -> list[dict]:
        with self.lock:
            ids = [row["id"] for row in self.db.execute(
                "SELECT id FROM clan WHERE instr(lower(name), lower(?)) > 0 ORDER BY id LIMIT 30",
                (keyword,),
            )]
            return [self.profile(clan_id) for clan_id in ids]

    def gold_spent(self, user_id: int) -> int:
        with self.lock:
            row = self.db.execute("SELECT gold FROM clan_spending WHERE user_id = ?", (user_id,)).fetchone()
            return row["gold"] if row else 0

    def change(self, user_id: int, action: str, request: dict, *, gold: int = 0) -> dict | None:
        with self.lock, self.db:
            clan_id = self.clan_id(user_id)
            now = int(time.time())
            if action == "create" and not clan_id:
                if gold < CLAN_CREATION_FEE:
                    return None
                name, desc, country = request.get("name"), request.get("description", ""), request.get("country", 0)
                if not isinstance(name, str) or not valid_text(name.strip(), 48) or not valid_text(desc, 240, empty=True):
                    return None
                if type(country) is not int or not 0 <= country <= 255 or request.get("openType", 0) != 0 or request.get("joinScore", 0) != 0:
                    return None
                cursor = self.db.execute(
                    "INSERT OR IGNORE INTO clan(owner, name, description, country, updated) VALUES (?, ?, ?, ?, ?)",
                    (user_id, name.strip(), desc, country, now),
                )
                if not cursor.rowcount:
                    return None
                clan_id = cursor.lastrowid
                self.db.execute("INSERT INTO membership VALUES (?, ?)", (user_id, clan_id))
                self.db.execute(
                    "INSERT INTO clan_spending VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET gold = gold + excluded.gold",
                    (user_id, CLAN_CREATION_FEE),
                )
            elif action == "join" and not clan_id:
                target = request.get("clanId")
                if type(target) is not int or not 0 < target < 2**63:
                    return None
                profile = self.profile(target)
                if profile is None or profile["memberCount"] >= MAX_MEMBERS:
                    return None
                clan_id = target
                self.db.execute("INSERT INTO membership VALUES (?, ?)", (user_id, clan_id))
            elif action == "leave" and clan_id:
                self.db.execute("DELETE FROM membership WHERE user_id = ?", (user_id,))
                successor = self.db.execute("SELECT min(user_id) FROM membership WHERE clan_id = ?", (clan_id,)).fetchone()[0]
                if successor is None:
                    self.db.execute("DELETE FROM chat WHERE clan_id = ?", (clan_id,))
                    self.db.execute("DELETE FROM clan WHERE id = ?", (clan_id,))
                else:
                    self.db.execute("UPDATE clan SET owner = ? WHERE id = ? AND owner = ?", (successor, clan_id, user_id))
                return {}
            elif action == "change-notice" and clan_id:
                notice = request.get("notice")
                if not valid_text(notice, 240, empty=True):
                    return None
                cursor = self.db.execute(
                    "UPDATE clan SET notice = ?, updated = ? WHERE id = ? AND owner = ?", (notice, now, clan_id, user_id),
                )
                if not cursor.rowcount:
                    return None
            else:
                return None
            self.db.execute("UPDATE clan SET updated = ? WHERE id = ?", (now, clan_id))
            return {"clanId": clan_id, "clan": self.profile(clan_id)}

    def history(self, clan_id: int) -> list[ChatMessage]:
        with self.lock:
            rows = self.db.execute(
                "SELECT user_id, name, text, time FROM chat WHERE clan_id = ? ORDER BY id DESC LIMIT ?",
                (clan_id, HISTORY_LIMIT),
            ).fetchall()
            return [ChatMessage(*row) for row in reversed(rows)]

    def post(self, user_id: int, text: str, *, clan: bool) -> tuple[int, ChatMessage] | None:
        if not valid_text(text, 127):
            return None
        with self.lock, self.db:
            clan_id = self.clan_id(user_id) if clan else 0
            if clan and not clan_id:
                return None
            now = int(time.time())
            message = ChatMessage(user_id, self.names[user_id], text, now)
            self.db.execute("INSERT INTO chat(clan_id, user_id, name, text, time) VALUES (?, ?, ?, ?, ?)",
                            (clan_id, user_id, message.name, text, now))
            self.db.execute("""DELETE FROM chat WHERE clan_id = ? AND id <=
                (SELECT id FROM chat WHERE clan_id = ? ORDER BY id DESC LIMIT 1 OFFSET ?)""",
                (clan_id, clan_id, HISTORY_LIMIT))
            return clan_id, message


def valid_text(value: object, limit: int, *, empty: bool = False) -> bool:
    if not isinstance(value, str) or (not empty and not value.strip()) or not value.isprintable() and value != "":
        return False
    try:
        return len(value.encode("utf-8")) <= limit
    except UnicodeEncodeError:
        return False
