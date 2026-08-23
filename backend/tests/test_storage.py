from datetime import datetime, timedelta, timezone

import pytest

from backend import storage


def test_create_user_returns_a_working_session_token():
    token = storage.create_user("alice", "correcthorse")
    assert storage.get_username_for_token(token) == "alice"


def test_create_user_rejects_duplicate_username():
    storage.create_user("alice", "correcthorse")
    with pytest.raises(storage.UsernameTaken):
        storage.create_user("alice", "anotherpassword")


def test_login_succeeds_with_correct_credentials():
    storage.create_user("alice", "correcthorse")
    token = storage.login("alice", "correcthorse")
    assert token is not None
    assert storage.get_username_for_token(token) == "alice"


def test_login_fails_with_wrong_password():
    storage.create_user("alice", "correcthorse")
    assert storage.login("alice", "wrongpassword") is None


def test_login_fails_for_unknown_user():
    assert storage.login("nobody", "whatever1") is None


def test_login_issues_a_new_token_each_time():
    storage.create_user("alice", "correcthorse")
    first = storage.login("alice", "correcthorse")
    second = storage.login("alice", "correcthorse")
    assert first != second
    # both sessions remain valid independently
    assert storage.get_username_for_token(first) == "alice"
    assert storage.get_username_for_token(second) == "alice"


def test_logout_invalidates_the_session():
    token = storage.create_user("alice", "correcthorse")
    storage.logout(token)
    assert storage.get_username_for_token(token) is None


def test_get_username_for_token_returns_none_for_unknown_token():
    assert storage.get_username_for_token("not-a-real-token") is None


def test_expired_session_is_rejected_and_reaped():
    token = storage.create_user("alice", "correcthorse")
    with storage._connect() as conn:
        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        conn.execute("UPDATE sessions SET expires_at = ? WHERE token = ?", (past, token))

    assert storage.get_username_for_token(token) is None
    # the lookup above should have deleted the expired row, not just ignored it
    with storage._connect() as conn:
        row = conn.execute("SELECT 1 FROM sessions WHERE token = ?", (token,)).fetchone()
    assert row is None


def test_plan_roundtrip_save_get_delete():
    storage.create_user("alice", "correcthorse")
    days = [{"weekday": "monday", "label": "Push", "exercises": [{"exercise_id": "0001", "done": False}]}]
    storage.save_plan("alice", "fr", days)

    stored = storage.get_plan("alice")
    assert stored == {"lang": "fr", "days": days}

    storage.delete_plan("alice")
    assert storage.get_plan("alice") is None


def test_save_plan_overwrites_existing_plan_for_same_user():
    storage.create_user("alice", "correcthorse")
    storage.save_plan("alice", "fr", [{"weekday": None, "label": "A", "exercises": []}])
    storage.save_plan("alice", "en", [{"weekday": None, "label": "B", "exercises": []}])

    stored = storage.get_plan("alice")
    assert stored["lang"] == "en"
    assert stored["days"][0]["label"] == "B"


def test_get_plan_returns_none_when_absent():
    assert storage.get_plan("nobody") is None
