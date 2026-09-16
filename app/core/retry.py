"""Retry with exponential backoff for VLM calls."""

import asyncio
import random

from app.core.exceptions import MaxRetriesExceededError, VLMError
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class RetryHandler:
    """Retry wrapper with exponential backoff and jitter."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        backoff_factor: float = 2.0,
        retryable_exceptions: tuple = (VLMError,),
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.retryable_exceptions = retryable_exceptions

    async def execute(self, func, *args, **kwargs):
        """Execute a function with retry logic.

        Args:
            func: Async function to execute.
            *args, **kwargs: Arguments to pass to the function.

        Returns:
            Result from the function.

        Raises:
            MaxRetriesExceededError: All retries exhausted.
        """
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except self.retryable_exceptions as e:
                last_exception = e

                if attempt == self.max_retries:
                    logger.error(
                        "max_retries_exceeded",
                        attempts=attempt + 1,
                        error=str(e),
                    )
                    raise MaxRetriesExceededError(
                        f"Failed after {self.max_retries + 1} attempts: {e}"
                    ) from e

                # Calculate delay with jitter
                delay = min(
                    self.base_delay * (self.backoff_factor ** attempt),
                    self.max_delay,
                )
                # Add jitter (±25%)
                jitter = delay * 0.25 * (2 * random.random() - 1)
                actual_delay = max(0.1, delay + jitter)

                logger.warning(
                    "retry_scheduled",
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    delay_seconds=round(actual_delay, 1),
                    error=str(e),
                )
                await asyncio.sleep(actual_delay)

        # Should never reach here, but just in case
        raise MaxRetriesExceededError(
            f"Unexpected retry loop exit after {self.max_retries} retries"
        )
