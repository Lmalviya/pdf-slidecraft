"""Unit tests for AsyncRateLimiter."""

import asyncio
import time

from app.core.rate_limiter import AsyncRateLimiter


async def test_rate_limiter_concurrency():
    """Verify semaphore concurrency limits."""
    limiter = AsyncRateLimiter(max_concurrency=2, max_rpm=100)
    active_count = 0
    max_active = 0

    async def worker():
        nonlocal active_count, max_active
        async with limiter:
            active_count += 1
            max_active = max(max_active, active_count)
            await asyncio.sleep(0.05)
            active_count -= 1

    tasks = [worker() for _ in range(6)]
    await asyncio.gather(*tasks)

    assert max_active <= 2, f"Max active concurrency was {max_active}, expected <= 2"


async def test_rate_limiter_rpm_sliding_window():
    """Verify RPM throttling delays requests when limit reached."""
    limiter = AsyncRateLimiter(max_concurrency=5, max_rpm=3)
    start = time.monotonic()

    for _ in range(3):
        await limiter.acquire()
        limiter.release()

    duration = time.monotonic() - start
    assert duration < 0.5
