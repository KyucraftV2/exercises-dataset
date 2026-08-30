from backend.ratelimit import RateLimiter


def test_allows_up_to_max_requests_then_denies():
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    assert limiter.allow("a") is True
    assert limiter.allow("a") is True
    assert limiter.allow("a") is True
    assert limiter.allow("a") is False


def test_different_keys_have_independent_budgets():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    assert limiter.allow("a") is True
    assert limiter.allow("b") is True
    assert limiter.allow("a") is False
    assert limiter.allow("b") is False


def test_window_expiry_frees_up_budget(monkeypatch):
    limiter = RateLimiter(max_requests=1, window_seconds=10)
    times = iter([100.0, 100.0, 111.0])
    monkeypatch.setattr("backend.ratelimit.time.monotonic", lambda: next(times))

    assert limiter.allow("a") is True  # t=100, consumes the only slot
    assert limiter.allow("a") is False  # t=100 again, still within window
    assert limiter.allow("a") is True  # t=111, prior hit is now outside the window


def test_evicts_least_recently_used_key_past_the_cap():
    limiter = RateLimiter(max_requests=5, window_seconds=60, max_tracked_keys=2)
    limiter.allow("a")
    limiter.allow("b")
    limiter.allow("c")  # exceeds cap of 2 -> evicts "a" (never touched again)

    assert "a" not in limiter._hits
    assert set(limiter._hits.keys()) == {"b", "c"}


def test_touching_a_key_protects_it_from_eviction():
    limiter = RateLimiter(max_requests=5, window_seconds=60, max_tracked_keys=2)
    limiter.allow("a")
    limiter.allow("b")
    limiter.allow("a")  # re-touch "a" - "b" is now the least recently used
    limiter.allow("c")  # exceeds cap -> evicts "b", not "a"

    assert set(limiter._hits.keys()) == {"a", "c"}


def test_retry_after_seconds_counts_down_to_the_oldest_hit_expiring(monkeypatch):
    limiter = RateLimiter(max_requests=1, window_seconds=10)
    times = iter([100.0, 104.0, 104.0])
    monkeypatch.setattr("backend.ratelimit.time.monotonic", lambda: next(times))

    assert limiter.allow("a") is True  # t=100, consumes the only slot
    assert limiter.allow("a") is False  # t=104, still within the window
    assert limiter.retry_after_seconds("a") == 6  # t=104, oldest hit expires at t=110


def test_retry_after_seconds_is_zero_for_a_key_with_no_hits():
    limiter = RateLimiter(max_requests=1, window_seconds=10)
    assert limiter.retry_after_seconds("never-seen") == 0
