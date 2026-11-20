"""Accounts, invitations, and player persistence for the community server."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import tempfile
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


USERNAME = re.compile(r"[A-Za-z0-9_]{3,20}")
SESSION_TOKEN = re.compile(r"acs_[A-Za-z0-9_-]{43}")
GATEWAY_TOKEN = re.compile(rb"\x2facp_[A-Za-z0-9_-]{43}(?![A-Za-z0-9_-])")
INVITE = re.compile(r"[A-Za-z0-9_-]{24}")
SESSION_SECONDS = 30 * 86400


class AccountError(ValueError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class PlayerIdentity:
    user_id: int
    username: str


def digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("ascii")).digest()


def gateway_token(session: str) -> str:
    value = digest("acies gateway " + session)
    return "acp_" + base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def gateway_credentials(payload: bytes) -> tuple[int, str] | None:
    # Opcode and protocol version precede Player::writeTo, which starts with the user ID.
    if len(payload) < 11 or payload[:3] != b"\x00\x12\x00":
        return None
    # The community build puts the session credential in the length-prefixed
    # locale field, whose offset varies with the preceding deck and inventory.
    match = GATEWAY_TOKEN.search(payload, 11)
    if match is None:
        return None
    return int.from_bytes(payload[3:11], "little"), match[0][1:].decode("ascii")


def password_bytes(value: object) -> bytes:
    if isinstance(value, str) and 12 <= len(value) <= 128:
        try:
            return value.encode("utf-8")
        except UnicodeEncodeError:
            pass
    raise AccountError(400, "Use a password with 12–128 characters.")


def password_hash(value: bytes, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", value, salt, 600_000)


class AccountStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.RLock()
        self.hash_slots = threading.BoundedSemaphore(4)
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA journal_mode = WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                salt BLOB NOT NULL, password_hash BLOB NOT NULL
            );
            CREATE TABLE IF NOT EXISTS invites (code_hash BLOB PRIMARY KEY, expires_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash BLOB PRIMARY KEY, gateway_hash BLOB NOT NULL UNIQUE,
                user_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE, expires_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at);
            CREATE TABLE IF NOT EXISTS player_state (
                user_id INTEGER NOT NULL REFERENCES accounts(id), key TEXT NOT NULL, value NOT NULL,
                PRIMARY KEY(user_id, key)
            );
            CREATE TABLE IF NOT EXISTS campaign_results (
                user_id INTEGER NOT NULL REFERENCES accounts(id), transaction_id INTEGER NOT NULL, result_json TEXT NOT NULL,
                PRIMARY KEY(user_id, transaction_id)
            );
            CREATE TABLE IF NOT EXISTS matches (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS match_results (
                match_id INTEGER NOT NULL REFERENCES matches(id), user_id INTEGER NOT NULL REFERENCES accounts(id),
                opponent_id INTEGER NOT NULL REFERENCES accounts(id), outcome INTEGER NOT NULL,
                PRIMARY KEY(match_id, user_id)
            );
            CREATE INDEX IF NOT EXISTS match_results_player ON match_results(user_id, match_id);
        """)

    def _hash(self, password: bytes, salt: bytes) -> bytes:
        if not self.hash_slots.acquire(blocking=False):
            raise AccountError(429, "The server is busy. Try again shortly.")
        try:
            return password_hash(password, salt)
        finally:
            self.hash_slots.release()

    def invite(self, hours: int) -> str:
        code = secrets.token_urlsafe(18)
        with self.lock, self.db:
            self.db.execute("DELETE FROM invites WHERE expires_at <= ?", (int(time.time()),))
            self.db.execute("INSERT INTO invites VALUES (?, ?)", (digest(code), int(time.time()) + hours * 3600))
        return code

    def register(self, username: object, password: object, invite: object, *, open_registration: bool) -> str:
        if not isinstance(username, str) or not USERNAME.fullmatch(username):
            raise AccountError(400, "Use 3–20 letters, numbers, or underscores for your username.")
        value = password_bytes(password)
        code = digest(invite) if isinstance(invite, str) and INVITE.fullmatch(invite) else None
        if not open_registration:
            with self.lock:
                valid = self.db.execute(
                    "SELECT 1 FROM invites WHERE code_hash = ? AND expires_at > ?", (code, int(time.time()))
                ).fetchone()
            if not valid:
                raise AccountError(403, "Enter a valid unused invitation code.")

        salt = secrets.token_bytes(16)
        hashed = self._hash(value, salt)
        with self.lock, self.db:
            if not open_registration and not self.db.execute(
                "DELETE FROM invites WHERE code_hash = ? AND expires_at > ?", (code, int(time.time()))
            ).rowcount:
                raise AccountError(403, "Enter a valid unused invitation code.")
            try:
                player = self.db.execute("INSERT INTO accounts(username, salt, password_hash) VALUES (?, ?, ?)",
                                         (username, salt, hashed)).lastrowid
            except sqlite3.IntegrityError:
                raise AccountError(409, "That username is already taken.") from None
            self.db.executemany("INSERT INTO player_state VALUES (?, ?, ?)",
                                [(player, "tutorial_stages", 0), (player, "tutorial_steps", "{}")])
            return self._session(player)

    def login(self, username: object, password: object) -> str:
        if not isinstance(username, str) or not USERNAME.fullmatch(username):
            raise AccountError(401, "Username or password is incorrect.")
        try:
            value = password_bytes(password)
        except AccountError:
            raise AccountError(401, "Username or password is incorrect.") from None
        with self.lock:
            row = self.db.execute("SELECT id, salt, password_hash FROM accounts WHERE username = ?", (username,)).fetchone()
        hashed = self._hash(value, row[1] if row else bytes(16))
        if row is None or not hmac.compare_digest(hashed, row[2]):
            raise AccountError(401, "Username or password is incorrect.")
        with self.lock, self.db:
            return self._session(row[0])

    def _session(self, user_id: int) -> str:
        token = "acs_" + secrets.token_urlsafe(32)
        now = int(time.time())
        self.db.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        self.db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?)",
                        (digest(token), digest(gateway_token(token)), user_id, now + SESSION_SECONDS))
        return token

    def authenticate(self, token: str) -> PlayerIdentity | None:
        if not SESSION_TOKEN.fullmatch(token):
            return None
        with self.lock:
            row = self.db.execute("""SELECT accounts.id, accounts.username FROM accounts JOIN sessions
                ON accounts.id = sessions.user_id WHERE sessions.token_hash = ? AND expires_at > ?""",
                (digest(token), int(time.time()))).fetchone()
        return PlayerIdentity(*row) if row else None

    def authenticate_gateway(self, payload: bytes) -> tuple[PlayerIdentity, bytes] | None:
        credentials = gateway_credentials(payload)
        if credentials is None:
            return None
        user_id, token = credentials
        if not 0 < user_id < 2**63:
            return None
        token_hash = digest(token)
        with self.lock:
            row = self.db.execute("""SELECT accounts.id, accounts.username FROM accounts JOIN sessions
                ON accounts.id = sessions.user_id WHERE sessions.gateway_hash = ? AND accounts.id = ? AND expires_at > ?""",
                (token_hash, user_id, int(time.time()))).fetchone()
        return (PlayerIdentity(*row), token_hash) if row else None

    def revoke(self, token: str) -> None:
        with self.lock, self.db:
            self.db.execute("DELETE FROM sessions WHERE token_hash = ?", (digest(token),))

    def gateway_valid(self, token_hash: bytes) -> bool:
        with self.lock:
            return self.db.execute("SELECT 1 FROM sessions WHERE gateway_hash = ? AND expires_at > ?",
                                   (token_hash, int(time.time()))).fetchone() is not None

    def players(self) -> dict[int, str]:
        with self.lock:
            return dict(self.db.execute("SELECT id, username FROM accounts"))

    def progress(self, user_id: int) -> tuple[dict, list]:
        with self.lock:
            saved = dict(self.db.execute("SELECT key, value FROM player_state WHERE user_id = ?", (user_id,)))
            battles = [json.loads(result) for result, in self.db.execute(
                "SELECT result_json FROM campaign_results WHERE user_id = ?", (user_id,))]
        return saved, battles

    def save_progress(self, user_id: int, key: str, value: str | int) -> None:
        with self.lock, self.db:
            self.db.execute("INSERT OR REPLACE INTO player_state VALUES (?, ?, ?)", (user_id, key, value))

    def save_campaign(self, user_id: int, stages: int | None, transaction: object, battle: object) -> bool:
        with self.lock, self.db:
            if isinstance(battle, dict) and type(transaction) is int and 0 < transaction < 2**63:
                if not self.db.execute("INSERT OR IGNORE INTO campaign_results VALUES (?, ?, ?)",
                                       (user_id, transaction, json.dumps(battle))).rowcount:
                    return False
            if stages is not None:
                self.db.execute("INSERT OR REPLACE INTO player_state VALUES (?, 'tutorial_stages', ?)", (user_id, stages))
            return True

    def create_match(self) -> int:
        with self.lock, self.db:
            return self.db.execute("INSERT INTO matches(created_at) VALUES (?)", (int(time.time()),)).lastrowid

    def save_match(self, match_id: int, users: tuple[int, int], results: tuple[int, int]) -> None:
        with self.lock, self.db:
            self.db.executemany("INSERT OR IGNORE INTO match_results VALUES (?, ?, ?, ?)",
                                [(match_id, users[0], users[1], results[0]), (match_id, users[1], users[0], results[1])])

    def match_counts(self, user_id: int) -> tuple[int, int]:
        with self.lock:
            return self.db.execute("SELECT COUNT(*), COUNT(CASE WHEN outcome = 1 THEN 1 END) FROM match_results WHERE user_id = ?",
                                   (user_id,)).fetchone()

    def backup(self, destination: Path) -> None:
        with tempfile.NamedTemporaryFile(prefix=".acies-backup-", dir=destination.parent, delete=False) as temporary:
            snapshot = Path(temporary.name)
        try:
            with self.lock, closing(sqlite3.connect(snapshot)) as backup:
                self.db.backup(backup)
            os.link(snapshot, destination)
        finally:
            snapshot.unlink()

    def close(self) -> None:
        with self.lock:
            self.db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    invite = commands.add_parser("invite", help="Print a single-use invitation code.")
    invite.add_argument("--hours", type=int, default=48)
    backup = commands.add_parser("backup", help="Make a consistent online SQLite backup.")
    backup.add_argument("destination", type=Path)
    args = parser.parse_args()
    if args.command == "invite" and not 1 <= args.hours <= 720:
        parser.error("invite lifetime must be between 1 and 720 hours")
    if args.command == "backup" and args.destination.exists():
        parser.error("backup destination already exists")
    db = AccountStore(args.database)
    try:
        if args.command == "invite":
            print(db.invite(args.hours))
        else:
            db.backup(args.destination)
    finally:
        db.close()


if __name__ == "__main__":
    main()
