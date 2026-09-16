"""Async Rate Limiter supporting concurrency limits and sliding-window RPM limits."""

from __future__ import annotations

import asyncio
import time
from collections import deque

from app.core.logging_config import get_logger

logger = get_logger(__name__)


class AsyncRateLimiter:
    """Thread-safe and async-safe rate limiter.

    Enforces:
    1. Maximum concurrent requests (Semaphore)
    2. Maximum requests per minute (Sliding window rate limit)
    """

    def __init__(self, max_concurrency: int = 2, max_rpm: int = 30):
        self.max_concurrency = max_concurrency
        self.max_rpm = max_rpm
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.request_timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until concurrency slot and rate limit quota are available."""
        # 1. Acquire concurrency slot
        await self.semaphore.acquire()

        # 2. Acquire RPM rate limit window slot
        async with self._lock:
            now = time.monotonic()

            # Remove timestamps older than 60 seconds
            while self.request_timestamps and now - self.request_timestamps[0] >= 60.0:
                self.request_timestamps.popleft()

            # If at or exceeding RPM limit, wait until oldest slot frees up
            if len(self.request_timestamps) >= self.max_rpm:
                sleep_duration = 60.0 - (now - self.request_timestamps[0]) + 0.05
                if sleep_duration > 0:
                    logger.warning(
                        "rate_limit_throttling",
                        reason="rpm_limit_reached",
                        sleep_s=round(sleep_duration, 2),
                        current_rpm=len(self.request_timestamps),
                        max_rpm=self.max_rpm,
                    )
                    await asyncio.sleep(sleep_duration)

                # Re-clean after sleep
                now = time.monotonic()
                while self.request_timestamps and now - self.request_timestamps[0] >= 60.0:
                    self.request_timestamps.popleft()

            self.request_timestamps.append(time.monotonic())

    def release(self) -> None:
        """Release the concurrency semaphore slot."""
        self.semaphore.release()

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.release()
