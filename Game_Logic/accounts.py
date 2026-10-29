import json
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from typing import Dict, Iterable, Optional

from werkzeug.security import check_password_hash, generate_password_hash

import security_questions

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
# Added after the first release, so they are created on older databases as well
USER_COLUMNS = {
    "portfolio_sub": "TEXT",
    "security_question": "TEXT",
    "security_answer_hash": "TEXT",
    "reset_failures": "INTEGER NOT NULL DEFAULT 0",
    "reset_locked_until": "REAL NOT NULL DEFAULT 0",
}


class AccountError(Exception):
    pass


def check_password(password: str):
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AccountError(f"Passwords need at least {MIN_PASSWORD_LENGTH} characters")


class Accounts:
    def __init__(self, path: str, secret_key: str):
        self.path = path
        self.secret_key = secret_key.encode("utf-8")
        with self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
            existing = {row[1] for row in db.execute("PRAGMA table_info(users)")}
            for column, kind in USER_COLUMNS.items():
                if column not in existing:
                    db.execute(f"ALTER TABLE users ADD COLUMN {column} {kind}")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_portfolio_sub ON users (portfolio_sub)")

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def register(self, username: str, password: str, question: str, answer: str) -> int:
        if not USERNAME_PATTERN.match(username):
            raise AccountError("Usernames are 3-20 letters, numbers, _ or -")
        check_password(password)
        problem = security_questions.problem(question, answer)
        if problem:
            raise AccountError(problem)
        try:
            with self._db() as db:
                cursor = db.execute(
                    """INSERT INTO users (username, password_hash, security_question, security_answer_hash)
                       VALUES (?, ?, ?, ?)""",
                    (username, generate_password_hash(password), question,
                     generate_password_hash(security_questions.normalize_answer(answer))))
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

    def linked_user(self, sub: str) -> Optional[int]:
        """The account linked to a portfolio account, or None"""
        with self._db() as db:
            row = db.execute("SELECT id FROM users WHERE portfolio_sub = ?", (sub,)).fetchone()
        return row[0] if row else None

    def link_portfolio(self, user_id: int, sub: str):
        try:
            with self._db() as db:
                linked = db.execute("UPDATE users SET portfolio_sub = ? WHERE id = ? AND portfolio_sub IS NULL",
                                    (sub, user_id)).rowcount
        except sqlite3.IntegrityError:
            raise AccountError("Your portfolio account is already linked to another account here")
        if not linked:
            raise AccountError("That account is already linked to another portfolio account")

    def portfolio_user(self, sub: str, username: str) -> int:
        """A new account linked to a portfolio account and named after it. Its password is random and never shown,
        so logging in with the portfolio account is the only way in."""
        base = username if USERNAME_PATTERN.match(username) else "player"
        n = 1
        while True:
            user_id = self.linked_user(sub)
            if user_id is not None:
                return user_id
            name = base if n == 1 else f"{base[:20 - len(str(n))]}{n}"
            try:
                with self._db() as db:
                    return db.execute("INSERT INTO users (username, password_hash, portfolio_sub) VALUES (?, ?, ?)",
                                      (name, generate_password_hash(secrets.token_urlsafe(32)), sub)).lastrowid
            except sqlite3.IntegrityError:
                # The name is taken, or a second login for this portfolio account got there first
                n += 1

    def has_security_question(self, user_id: int) -> bool:
        with self._db() as db:
            row = db.execute("SELECT security_answer_hash FROM users WHERE id = ?", (user_id,)).fetchone()
        return bool(row and row[0])

    def set_security_question(self, user_id: int, question: str, answer: str):
        problem = security_questions.problem(question, answer)
        if problem:
            raise AccountError(problem)
        with self._db() as db:
            db.execute("UPDATE users SET security_question = ?, security_answer_hash = ? WHERE id = ?",
                       (question, generate_password_hash(security_questions.normalize_answer(answer)), user_id))

    def security_question(self, username: str) -> str:
        with self._db() as db:
            row = db.execute("SELECT security_question FROM users WHERE username = ? AND security_answer_hash IS NOT NULL",
                             (username,)).fetchone()
        return row[0] if row else security_questions.stand_in_question(username, self.secret_key)

    def reset_password(self, username: str, answer: str, new_password: str):
        """Sets a new password when the security answer is right. Too many wrong answers lock resets for a while."""
        check_password(new_password)
        with self._db() as db:
            row = db.execute("""SELECT id, security_answer_hash, reset_failures, reset_locked_until FROM users
                                WHERE username = ? AND security_answer_hash IS NOT NULL""", (username,)).fetchone()
        if row is None:
            check_password_hash(DUMMY_HASH, answer)
            raise AccountError("That answer is wrong")
        user_id, answer_hash, failures, locked_until = row
        if time.time() < locked_until:
            raise AccountError("Too many wrong answers. Try again in 15 minutes.")
        if not check_password_hash(answer_hash, security_questions.normalize_answer(answer)):
            failures += 1
            locked = failures >= security_questions.MAX_RESET_FAILURES
            with self._db() as db:
                db.execute("UPDATE users SET reset_failures = ?, reset_locked_until = ? WHERE id = ?",
                           (0 if locked else failures,
                            time.time() + security_questions.RESET_LOCK_SECONDS if locked else 0, user_id))
            raise AccountError("That answer is wrong")
        with self._db() as db:
            db.execute("UPDATE users SET password_hash = ?, reset_failures = 0, reset_locked_until = 0 WHERE id = ?",
                       (generate_password_hash(new_password), user_id))

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
