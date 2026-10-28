import json
import re
import sqlite3
from contextlib import contextmanager
from typing import Dict, Iterable, Optional

from werkzeug.security import check_password_hash, generate_password_hash

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,20}$")
MIN_PASSWORD_LENGTH = 8

# Checked against when the username doesn't exist, so a wrong username takes as long as a wrong password
DUMMY_HASH = generate_password_hash("not a real password")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS saves (
    user_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    data TEXT NOT NULL,
    last_saved REAL NOT NULL,
    PRIMARY KEY (user_id, name)
);
CREATE TABLE IF NOT EXISTS records (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    achievements TEXT NOT NULL,
    devoured TEXT NOT NULL
);
"""


class AccountError(Exception):
    pass


class Accounts:
    def __init__(self, path: str):
        self.path = path
        with self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def register(self, username: str, password: str) -> int:
        if not USERNAME_PATTERN.match(username):
            raise AccountError("Usernames are 3-20 letters, numbers, _ or -")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise AccountError(f"Passwords need at least {MIN_PASSWORD_LENGTH} characters")
        try:
            with self._db() as db:
                cursor = db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                                    (username, generate_password_hash(password)))
                return cursor.lastrowid
        except sqlite3.IntegrityError:
            raise AccountError("That username is taken")

    def check_login(self, username: str, password: str) -> int:
        with self._db() as db:
            row = db.execute("SELECT id, password_hash FROM users WHERE username = ?", (username,)).fetchone()
        if row is None:
            check_password_hash(DUMMY_HASH, password)
            raise AccountError("Wrong username or password")
        if not check_password_hash(row[1], password):
            raise AccountError("Wrong username or password")
        return row[0]

    def username(self, user_id: int) -> Optional[str]:
        with self._db() as db:
            row = db.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
        return row[0] if row else None

    def store_save(self, user_id: int, save: Dict):
        """Keep the newer copy when a save with this name is already stored"""
        with self._db() as db:
            db.execute(
                """INSERT INTO saves (user_id, name, data, last_saved) VALUES (?, ?, ?, ?)
                   ON CONFLICT (user_id, name) DO UPDATE SET data = excluded.data, last_saved = excluded.last_saved
                   WHERE excluded.last_saved >= saves.last_saved""",
                (user_id, save["player_name"], json.dumps(save), save["last_saved"]),
            )

    def delete_save(self, user_id: int, name: str):
        with self._db() as db:
            db.execute("DELETE FROM saves WHERE user_id = ? AND name = ?", (user_id, name))

    def store_record(self, user_id: int, achievements: Iterable[str], devoured: Dict[str, int]):
        """Combine achievements, and keep the higher devour count per difficulty so the same
        world is never counted twice"""
        current = self.load_record(user_id)
        merged_achievements = sorted(set(current["achievements"]) | set(achievements))
        merged_devoured = dict(current["devoured"])
        for difficulty, count in devoured.items():
            merged_devoured[difficulty] = max(merged_devoured.get(difficulty, 0), count)
        if merged_achievements == sorted(current["achievements"]) and merged_devoured == current["devoured"]:
            return
        with self._db() as db:
            db.execute(
                """INSERT INTO records (user_id, achievements, devoured) VALUES (?, ?, ?)
                   ON CONFLICT (user_id) DO UPDATE SET achievements = excluded.achievements,
                   devoured = excluded.devoured""",
                (user_id, json.dumps(merged_achievements), json.dumps(merged_devoured)),
            )

    def load_record(self, user_id: int) -> Dict:
        with self._db() as db:
            record = db.execute("SELECT achievements, devoured FROM records WHERE user_id = ?", (user_id,)).fetchone()
        return {
            "achievements": json.loads(record[0]) if record else [],
            "devoured": json.loads(record[1]) if record else {},
        }

    def load(self, user_id: int) -> Dict:
        with self._db() as db:
            saves = db.execute("SELECT name, data FROM saves WHERE user_id = ?", (user_id,)).fetchall()
        return {"saves": {name: json.loads(data) for name, data in saves}, **self.load_record(user_id)}
