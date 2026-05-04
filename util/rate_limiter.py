import asyncio
import time


class TokenBucket:
    """Token bucket rate limiter with 429 exponential backoff.

    Pacing: token-bucket algorithm (tokens refill at `rate`/sec, burst capacity).
    429 handling (ported from NASE3): server Retry-After > exponential backoff >
    progressive cooldown after repeated 429s. handle_success() resets backoff.
    """

    _RETRY_DELAYS = [6.0, 12.0, 24.0, 48.0, 60.0]
    _COOLDOWN_REPEATED_429 = 60.0
    _REPEATED_429_THRESHOLD = 3

    def __init__(self, rate: float, burst: int = 1):
        self._rate = max(rate, 0.01)
        self._burst = max(burst, 1)
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

        # 429 backoff state (ported from NASE3 SlidingWindowRateLimiter)
        self._consecutive_429s: int = 0
        self._total_429s: int = 0
        self._total_requests: int = 0
        self._retry_index: int = 0
        self._next_allowed_at: float = 0.0
        self._current_delay: float = 1.0 / rate

    # ---- Token pacing ----

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
        self._last_refill = now

    async def acquire(self) -> None:
        async with self._lock:
            # Cool-down gate (ported from NASE3 acquire())
            now = time.monotonic()
            if now < self._next_allowed_at:
                wait = self._next_allowed_at - now
                await asyncio.sleep(wait)
                now = time.monotonic()

            while self._tokens < 1.0:
                wait = (1.0 - self._tokens) / self._rate
                await asyncio.sleep(wait)
                now = time.monotonic()
                self._refill()
                if self._next_allowed_at > now:
                    extra = self._next_allowed_at - now
                    await asyncio.sleep(extra)
                    now = time.monotonic()

            self._tokens -= 1.0
            self._total_requests += 1

    def available_in(self) -> float:
        """Seconds until next token or cooldown expires (for TUI display)."""
        self._refill()
        pacing_wait = 0.0 if self._tokens >= 1.0 else (1.0 - self._tokens) / self._rate
        now = time.monotonic()
        backoff_wait = max(0.0, self._next_allowed_at - now)
        return max(pacing_wait, backoff_wait)

    # ---- 429 backoff (ported from NASE3) ----

    def handle_429(self, retry_after: float | None = None) -> None:
        """Handle a 429 response. Call when HTTP 429 is received."""
        self._consecutive_429s += 1
        self._total_429s += 1

        if retry_after and retry_after > 0:
            delay = retry_after
        else:
            idx = self._retry_index
            if idx < len(self._RETRY_DELAYS):
                delay = self._RETRY_DELAYS[idx]
                self._retry_index = min(idx + 1, len(self._RETRY_DELAYS) - 1)
            else:
                delay = self._RETRY_DELAYS[-1]

        if self._consecutive_429s > self._REPEATED_429_THRESHOLD:
            delay += self._COOLDOWN_REPEATED_429

        self._next_allowed_at = time.monotonic() + delay
        self._current_delay = max(self._current_delay, delay)

    def handle_success(self) -> None:
        """Reset backoff state after a successful request."""
        if self._consecutive_429s > 0:
            self._consecutive_429s = 0
            self._retry_index = 0
            self._current_delay = 1.0 / self._rate

    # ---- Telemetry (ported from NASE3 get_status()) ----

    @property
    def status(self) -> dict:
        """Rich telemetry for TUI display."""
        now = time.monotonic()
        wait = max(0.0, self._next_allowed_at - now)
        total = self._total_requests + self._total_429s
        return {
            "rate_limited": self._consecutive_429s > 0 and now < self._next_allowed_at,
            "consecutive_429s": self._consecutive_429s,
            "total_429s": self._total_429s,
            "time_until_next": wait,
            "current_delay": self._current_delay,
            "total_requests": self._total_requests,
            "success_rate": round((self._total_requests / total * 100) if total > 0 else 100.0, 1),
        }

    @property
    def rate(self) -> float:
        return self._rate
