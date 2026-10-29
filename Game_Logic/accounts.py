import hashlib
import json
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from typing import Callable, Dict, Iterable, Optional

from werkzeug.security import check_password_hash, generate_password_hash

from ronovo_portfolio_auth import security_questions
from ronovo_portfolio_auth.login_limiter import LockedOut, LoginLimiter

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,20}$")
MIN_PASSWORD_LENGTH = 8

# Checked against when the username doesn't exist, so a wrong username takes as long as a wrong password
DUMMY_HASH = generate_password_hash("not a real password")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    portfolio_sub TEXT UNIQUE,
    security_question TEXT,
    security_answer_hash TEXT,
    reset_failures INTEGER NOT NULL DEFAULT 0,
    reset_locked_until REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS saves (
    user_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    data TEXT NOT NULL,
    last_saved REAL NOT NULL,
    PRIMARY KEY (user_id, name)
);
CREATE TABLE IF NOT EXISTS deleted_saves (
    user_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    deleted_at REAL NOT NULL,
    PRIMARY KEY (user_id, name)
);
CREATE TABLE IF NOT EXISTS records (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    achievements TEXT NOT NULL,
    devoured TEXT NOT NULL
);
"""


# Worlds an account can keep. Saves arrive from the browser, so this stops one account filling the disk.
MAX_SAVES = 50


class AccountError(Exception):
    pass


def check_password(password: str):
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AccountError(f"Passwords need at least {MIN_PASSWORD_LENGTH} characters")


class Accounts:
    def __init__(self, path: str, secret_key: str):
        self.path = path
        self.secret_key = secret_key.encode("utf-8")
        self._logins = LoginLimiter()
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
        try:
            valid = self._logins.attempt(username, lambda: check_password_hash(row[1] if row else DUMMY_HASH, password)
                                         and row is not None)
        except LockedOut as locked:
            raise AccountError(str(locked)) from None
        if not valid:
            raise AccountError("Wrong username or password")
        return row[0]

    def username(self, user_id: int) -> Optional[str]:
        with self._db() as db:
            row = db.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
        return row[0] if row else None

    def session_key(self, user_id: int) -> Optional[str]:
        """Changes whenever the password does, so a login session stored with it ends when the password is
        reset. None when the account no longer exists."""
        with self._db() as db:
            row = db.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
        return hashlib.sha256(row[0].encode("utf-8")).hexdigest()[:16] if row else None

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

    def security_question(self, username: str) -> str:
        with self._db() as db:
            row = db.execute("SELECT security_question FROM users WHERE username = ? AND security_answer_hash IS NOT NULL",
                             (username,)).fetchone()
        return row[0] if row else security_questions.stand_in_question(username, self.secret_key)

    def reset_password(self, username: str, answer: str, new_password: str):
        """Sets a new password when the security answer is right. Too many wrong answers lock resets for a while."""
        check_password(new_password)
        with self._db() as db:
            row = db.execute("""SELECT id, security_answer_hash FROM users
                                WHERE username = ? AND security_answer_hash IS NOT NULL""", (username,)).fetchone()
        if row is None:
            check_password_hash(DUMMY_HASH, answer)
            raise AccountError("That answer is wrong")
        user_id, answer_hash = row
        # Each try is counted before the answer is checked, in one statement, so answers sent at the same
        # moment can't all slip in under the limit.
        with self._db() as db:
            counted = db.execute("""UPDATE users SET reset_failures = reset_failures + 1
                                    WHERE id = ? AND reset_locked_until <= ? RETURNING reset_failures""",
                                 (user_id, time.time())).fetchone()
        if counted is None or counted[0] > security_questions.MAX_RESET_FAILURES:
            raise AccountError("Too many wrong answers. Try again in 15 minutes.")
        if not check_password_hash(answer_hash, security_questions.normalize_answer(answer)):
            if counted[0] == security_questions.MAX_RESET_FAILURES:
                with self._db() as db:
                    db.execute("UPDATE users SET reset_failures = 0, reset_locked_until = ? WHERE id = ?",
                               (time.time() + security_questions.RESET_LOCK_SECONDS, user_id))
            raise AccountError("That answer is wrong")
        with self._db() as db:
            db.execute("UPDATE users SET password_hash = ?, reset_failures = 0, reset_locked_until = 0 WHERE id = ?",
                       (generate_password_hash(new_password), user_id))

    def store_save(self, user_id: int, save: Dict, rank: Callable[[Dict], tuple]):
        """Keeps whichever copy of a save ranks higher when one with this name is already stored. A new name is
        refused once the account holds MAX_SAVES. A copy last saved before its name was deleted stays deleted;
        one saved after it is a new world and clears the deletion."""
        with self._db() as db:
            deleted = db.execute("SELECT deleted_at FROM deleted_saves WHERE user_id = ? AND name = ?",
                                 (user_id, save["player_name"])).fetchone()
            if deleted is not None:
                if save["last_saved"] <= deleted[0]:
                    return
                db.execute("DELETE FROM deleted_saves WHERE user_id = ? AND name = ?",
                           (user_id, save["player_name"]))
            stored = db.execute("SELECT data FROM saves WHERE user_id = ? AND name = ?",
                                (user_id, save["player_name"])).fetchone()
            if stored is None:
                if db.execute("SELECT COUNT(*) FROM saves WHERE user_id = ?", (user_id,)).fetchone()[0] >= MAX_SAVES:
                    return
            elif rank(json.loads(stored[0])) > rank(save):
                return
            db.execute(
                """INSERT INTO saves (user_id, name, data, last_saved) VALUES (?, ?, ?, ?)
                   ON CONFLICT (user_id, name) DO UPDATE SET data = excluded.data, last_saved = excluded.last_saved""",
                (user_id, save["player_name"], json.dumps(save), save["last_saved"]),
            )

    def delete_save(self, user_id: int, name: str):
        """Deletes the world and remembers that it was deleted, so another browser's copy doesn't bring it back."""
        with self._db() as db:
            db.execute("DELETE FROM saves WHERE user_id = ? AND name = ?", (user_id, name))
            db.execute(
                """INSERT INTO deleted_saves (user_id, name, deleted_at) VALUES (?, ?, ?)
                   ON CONFLICT (user_id, name) DO UPDATE SET deleted_at = excluded.deleted_at""",
                (user_id, name, time.time()),
            )

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
            deleted = db.execute("SELECT name FROM deleted_saves WHERE user_id = ?", (user_id,)).fetchall()
        return {"saves": {name: json.loads(data) for name, data in saves}, "deleted": sorted(name for name, in deleted),
                **self.load_record(user_id)}
