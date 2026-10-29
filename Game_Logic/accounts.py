import hashlib
import json
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from typing import Callable, Dict, Iterable, Optional, Tuple

from werkzeug.security import check_password_hash, generate_password_hash

from ronovo_portfolio_auth import security_questions
from ronovo_portfolio_auth.login_limiter import LockedOut, LoginLimiter

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,20}$")
MIN_PASSWORD_LENGTH = 8
NO_ACCOUNT = "There is no account with that username"

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
    world_id TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (user_id, name)
);
CREATE TABLE IF NOT EXISTS deleted_worlds (
    user_id INTEGER NOT NULL REFERENCES users(id),
    world_id TEXT NOT NULL,
    deleted_at REAL NOT NULL,
    PRIMARY KEY (user_id, world_id)
);
CREATE TABLE IF NOT EXISTS records (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    achievements TEXT NOT NULL,
    devours TEXT NOT NULL
);
"""


# Saves and deletes arrive from the browser, so these stop one account filling the disk. Only the newest
# MAX_DELETED deleted worlds are remembered.
MAX_SAVES = 50
MAX_DELETED = 200

Devour = Tuple[str, int, str]


class AccountError(Exception):
    pass


def check_password(password: str):
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AccountError(f"Passwords need at least {MIN_PASSWORD_LENGTH} characters")


def _forget(db, user_id: int, world_id: str):
    """Deletes a world and remembers that it was deleted, so another browser's copy doesn't bring it back."""
    db.execute("DELETE FROM saves WHERE user_id = ? AND world_id = ?", (user_id, world_id))
    db.execute("""INSERT INTO deleted_worlds (user_id, world_id, deleted_at) VALUES (?, ?, ?)
                  ON CONFLICT (user_id, world_id) DO UPDATE SET deleted_at = excluded.deleted_at""",
               (user_id, world_id, time.time()))
    db.execute("""DELETE FROM deleted_worlds WHERE user_id = ? AND world_id NOT IN (
                      SELECT world_id FROM deleted_worlds WHERE user_id = ? ORDER BY deleted_at DESC LIMIT ?)""",
               (user_id, user_id, MAX_DELETED))


class Accounts:
    def __init__(self, path: str):
        self.path = path
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

    @contextmanager
    def _write(self):
        """A transaction that takes the write lock before it reads, so two requests can't both read a row and
        then each write back their own copy."""
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
            except BaseException:
                db.execute("ROLLBACK")
                raise
            db.execute("COMMIT")
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
            valid = self._logins.attempt(username, lambda: row is not None and check_password_hash(row[1], password))
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

    def _reset_account(self, username: str) -> Tuple[int, str, str]:
        """(id, security question, answer hash) of the account a password reset is for."""
        with self._db() as db:
            row = db.execute("SELECT id, security_question, security_answer_hash FROM users WHERE username = ?",
                             (username,)).fetchone()
        if row is None:
            raise AccountError(NO_ACCOUNT)
        if row[2] is None:
            raise AccountError("That account has no security question. Log in with your portfolio account.")
        return row

    def security_question(self, username: str) -> str:
        return self._reset_account(username)[1]

    def reset_password(self, username: str, answer: str, new_password: str):
        """Sets a new password when the security answer is right. Too many wrong answers lock resets for a while."""
        check_password(new_password)
        user_id, _, answer_hash = self._reset_account(username)
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

    def store_save(self, user_id: int, save: Dict, rank: Callable[[Dict], tuple], started: Callable[[Dict], float]):
        """Keeps whichever copy of a world ranks higher. A different world under a stored world's name replaces it
        when it began later, and whichever world loses is deleted. Deleted worlds stay deleted, and a new name is
        refused once the account holds MAX_SAVES."""
        world_id, name = save["world_id"], save["player_name"]
        with self._write() as db:
            if db.execute("SELECT 1 FROM deleted_worlds WHERE user_id = ? AND world_id = ?",
                          (user_id, world_id)).fetchone():
                return
            stored = db.execute("SELECT data FROM saves WHERE user_id = ? AND name = ?", (user_id, name)).fetchone()
            if stored is None:
                if db.execute("SELECT COUNT(*) FROM saves WHERE user_id = ?", (user_id,)).fetchone()[0] >= MAX_SAVES:
                    return
            else:
                stored = json.loads(stored[0])
                if stored["world_id"] == world_id:
                    if rank(stored) > rank(save):
                        return
                elif started(stored) > started(save):
                    _forget(db, user_id, world_id)
                    return
                else:
                    _forget(db, user_id, stored["world_id"])
            db.execute(
                """INSERT INTO saves (user_id, name, world_id, data) VALUES (?, ?, ?, ?)
                   ON CONFLICT (user_id, name) DO UPDATE SET world_id = excluded.world_id, data = excluded.data""",
                (user_id, name, world_id, json.dumps(save)),
            )

    def delete_worlds(self, user_id: int, world_ids: Iterable[str]):
        with self._write() as db:
            for world_id in world_ids:
                _forget(db, user_id, world_id)

    def store_record(self, user_id: int, achievements: Iterable[str], devours: Iterable[Devour]):
        """Combines achievements and devours with the account's. A devour is counted once however many browsers
        report it."""
        with self._write() as db:
            current = self._record(db, user_id)
            merged_achievements = sorted(set(current["achievements"]) | set(achievements))
            merged_devours = sorted(set(current["devours"]) | set(devours))
            if merged_achievements == current["achievements"] and merged_devours == current["devours"]:
                return
            db.execute(
                """INSERT INTO records (user_id, achievements, devours) VALUES (?, ?, ?)
                   ON CONFLICT (user_id) DO UPDATE SET achievements = excluded.achievements,
                   devours = excluded.devours""",
                (user_id, json.dumps(merged_achievements), json.dumps(merged_devours)),
            )

    @staticmethod
    def _record(db, user_id: int) -> Dict:
        record = db.execute("SELECT achievements, devours FROM records WHERE user_id = ?", (user_id,)).fetchone()
        return {
            "achievements": sorted(json.loads(record[0])) if record else [],
            "devours": sorted(tuple(devour) for devour in json.loads(record[1])) if record else [],
        }

    def load(self, user_id: int) -> Dict:
        with self._db() as db:
            saves = db.execute("SELECT name, data FROM saves WHERE user_id = ?", (user_id,)).fetchall()
            deleted = db.execute("SELECT world_id FROM deleted_worlds WHERE user_id = ?", (user_id,)).fetchall()
            record = self._record(db, user_id)
        return {"saves": {name: json.loads(data) for name, data in saves},
                "deleted": sorted(world_id for world_id, in deleted), **record}
