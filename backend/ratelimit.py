"""In-memory sliding-window rate limiting.

Single-process only - state lives in a plain dict, so it resets on restart
and isn't shared across multiple workers/instances. That matches how this
app is actually run (one `uvicorn` process); a multi-instance deployment
would need a shared store (e.g. Redis) instead.
"""

import time
from collections import defaultdict, deque
from threading import Lock


class RateLimiter:
    """Allows at most `max_requests` calls to `allow(key)` per `key` within
    any rolling `window_seconds` window."""

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window_seconds:
                hits.popleft()
            if len(hits) >= self.max_requests:
                return False
            hits.append(now)
            return True
