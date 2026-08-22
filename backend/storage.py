import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import auth

DB_PATH = Path(__file__).resolve().parent / "app.db"


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                username TEXT NOT NULL REFERENCES users(username),
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plans (
                username TEXT PRIMARY KEY REFERENCES users(username),
                lang TEXT NOT NULL,
                days_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class UsernameTaken(Exception):
    pass


def create_user(username: str, password: str) -> str:
    """Create a user and an initial session, returning its token."""
    with _connect() as conn:
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, auth.hash_password(password), _now()),
            )
        except sqlite3.IntegrityError as exc:
            raise UsernameTaken(username) from exc
        token = auth.generate_token()
        conn.execute(
            "INSERT INTO sessions (token, username, created_at) VALUES (?, ?, ?)",
            (token, username, _now()),
        )
        return token


def login(username: str, password: str) -> str | None:
    """Verify credentials and create a new session, returning its token, or
    None if the username/password combination is invalid."""
    with _connect() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE username = ?", (username,)).fetchone()
        # Always run the (expensive) hash check, even for a username that
        # doesn't exist - otherwise a missing user short-circuits and
        # returns ~600k PBKDF2 iterations faster than a wrong password for
        # a real one, letting an attacker enumerate registered usernames
        # purely from response timing.
        password_hash = row["password_hash"] if row is not None else auth.DUMMY_HASH
        password_ok = auth.verify_password(password, password_hash)
        if row is None or not password_ok:
            return None
        token = auth.generate_token()
        conn.execute(
            "INSERT INTO sessions (token, username, created_at) VALUES (?, ?, ?)",
            (token, username, _now()),
        )
        return token


def logout(token: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def get_username_for_token(token: str) -> str | None:
    with _connect() as conn:
        row = conn.execute("SELECT username FROM sessions WHERE token = ?", (token,)).fetchone()
        return row["username"] if row else None


def get_plan(username: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT lang, days_json FROM plans WHERE username = ?", (username,)).fetchone()
        if row is None:
            return None
        return {"lang": row["lang"], "days": json.loads(row["days_json"])}


def save_plan(username: str, lang: str, days: list[dict]) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO plans (username, lang, days_json, updated_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET lang = excluded.lang,
                                                 days_json = excluded.days_json,
                                                 updated_at = excluded.updated_at
            """,
            (username, lang, json.dumps(days), _now()),
        )


def delete_plan(username: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM plans WHERE username = ?", (username,))
