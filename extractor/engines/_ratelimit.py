# LOGIC HEADER
# Input:          A requests-per-minute budget; for backoff, an attempt number.
# Transformation: RateLimiter spaces calls so they stay under a per-minute cap (free
#                 tiers reject bursts). backoff_delay computes an exponentially growing
#                 wait for retrying after a rate-limit/transient error. The clock and
#                 sleep functions are injectable so the timing logic is unit-testable
#                 without real waiting.
# Output:         Paced execution (RateLimiter.wait blocks as needed); a delay in
#                 seconds (backoff_delay).

from __future__ import annotations

import time
from typing import Callable


class RateLimiter:
    """Blocks just long enough between calls to stay under `per_minute` requests."""

    def __init__(self, per_minute: float,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.min_interval = (60.0 / per_minute) if per_minute and per_minute > 0 else 0.0
        self._sleep = sleep
        self._clock = clock
        self._last: float | None = None

    def wait(self) -> None:
        if self.min_interval <= 0:
            return
        now = self._clock()
        if self._last is not None:
            elapsed = now - self._last
            remaining = self.min_interval - elapsed
            if remaining > 0:
                self._sleep(remaining)
        self._last = self._clock()


def backoff_delay(attempt: int, base: float = 2.0, cap: float = 60.0) -> float:
    """Exponential backoff: base, 2*base, 4*base, ... capped. attempt is 0-based."""
    if attempt < 0:
        attempt = 0
    return min(cap, base * (2 ** attempt))
