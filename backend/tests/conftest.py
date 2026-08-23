import pytest
from fastapi.testclient import TestClient

from backend import main, storage

CSRF_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture(autouse=True)
def force_local_ai_mode(monkeypatch):
    """AI_MODE=claude (with a real ANTHROPIC_API_KEY) may be set in a
    developer's local .env - never let a test suite run hit the paid Claude
    API. local mode needs no API key and no network access."""
    monkeypatch.setenv("AI_MODE", "local")


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Every test gets its own empty SQLite file - storage.py reads
    storage.DB_PATH at call time (not captured at import), so patching the
    module attribute is enough to redirect every connection."""
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    storage.init_db()
    yield


@pytest.fixture(autouse=True)
def reset_rate_limiters():
    """The rate limiters in backend.main are module-level singletons keyed
    by username/IP - TestClient always uses the same fake client IP, so
    without a reset, unrelated tests would trip each other's limits."""
    for limiter in (main.CHAT_RATE_LIMIT, main.LOGIN_RATE_LIMIT, main.REGISTER_RATE_LIMIT):
        limiter._hits.clear()
    yield


@pytest.fixture
def client():
    # The session cookie is Secure - TestClient's default base_url is plain
    # http, under which httpx's cookie jar silently drops it after the
    # first response instead of sending it back. Use an https base_url so
    # the cookie actually round-trips like it would with a real browser.
    return TestClient(main.app, base_url="https://testserver")
