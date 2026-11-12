"""Rate limiting: at most `limit` requests per user in any `window` seconds.

Over the limit, the API answers 429 Too Many Requests with a Retry-After
header saying how many seconds to wait. Counts are kept in memory, per
process; with several server processes you would keep them in a shared
store such as Redis.
"""

import math
import threading
import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import Depends, HTTPException, status

from askboard import config
from askboard.auth import User, current_user


class RateLimiter:
    def __init__(self, limit: int, window: float) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self.window:  # forget old requests
                hits.popleft()
            if len(hits) >= self.limit:
                retry_after = math.ceil(hits[0] + self.window - now)
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    "Too many requests, slow down",
                    headers={"Retry-After": str(retry_after)},
                )
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


writes = RateLimiter(config.RATE_LIMIT, config.RATE_WINDOW)


def limited_user(user: Annotated[User, Depends(current_user)]) -> User:
    """The logged-in user, if they are still under the rate limit."""
    writes.check(user.name)
    return user


LimitedUser = Annotated[User, Depends(limited_user)]
