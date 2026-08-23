"""In-memory sliding-window rate limiting.

Single-process only - state lives in a plain dict, so it resets on restart
and isn't shared across multiple workers/instances. That matches how this
app is actually run (one `uvicorn` process); a multi-instance deployment
would need a shared store (e.g. Redis) instead.
"""

import time
from collections import OrderedDict, deque
from threading import Lock

DEFAULT_MAX_TRACKED_KEYS = 10_000


class RateLimiter:
    """Allows at most `max_requests` calls to `allow(key)` per `key` within
    any rolling `window_seconds` window.

    Tracks at most `max_tracked_keys` distinct keys at once, evicting the
    least-recently-used one past that cap - otherwise a key that's only ever
    seen once (e.g. a rotating attacker IP) would sit in memory forever,
    since its entry is only cleaned up lazily on its own next call."""

    def __init__(
        self, max_requests: int, window_seconds: float, max_tracked_keys: int = DEFAULT_MAX_TRACKED_KEYS
    ) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_tracked_keys = max_tracked_keys
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                hits = deque()
                self._hits[key] = hits
                if len(self._hits) > self.max_tracked_keys:
                    self._hits.popitem(last=False)
            else:
                self._hits.move_to_end(key)

            while hits and now - hits[0] > self.window_seconds:
                hits.popleft()
            if len(hits) >= self.max_requests:
                return False
            hits.append(now)
            return True
