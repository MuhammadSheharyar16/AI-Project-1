"""Per-client rate limiting (the security headers live in app/middlewares)."""

import threading
import time
from collections import defaultdict, deque


class ClientRateLimiter:
    """Sliding one-minute window per client key (IP address)."""

    MAX_CLIENTS = 10_000  # bound memory: forget idle clients when this many are tracked

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, client: str) -> bool:
        now = time.monotonic()
        with self._lock:
            if len(self._hits) > self.MAX_CLIENTS:
                self._hits = defaultdict(deque, {k: v for k, v in self._hits.items() if v and now - v[-1] < 60})
            hits = self._hits[client]
            while hits and now - hits[0] >= 60:
                hits.popleft()
            if len(hits) >= self.per_minute:
                return False
            hits.append(now)
            return True
