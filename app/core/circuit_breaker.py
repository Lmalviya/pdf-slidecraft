"""Circuit breaker pattern to protect against sustained Ollama failures."""

import time

from app.core.exceptions import CircuitBreakerOpenError
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class CircuitBreaker:
    """Circuit breaker with three states: CLOSED → OPEN → HALF_OPEN.

    - CLOSED: Normal operation. Failures are counted.
    - OPEN: All calls are rejected immediately. Entered after failure_threshold failures.
    - HALF_OPEN: A limited number of test calls are allowed after recovery_timeout.
                 Success resets to CLOSED; failure returns to OPEN.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 2,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state = "CLOSED"
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._half_open_calls = 0

    @property
    def state(self) -> str:
        """Current circuit breaker state."""
        return self._state

    @property
    def is_closed(self) -> bool:
        return self._state == "CLOSED"

    async def call(self, func, *args, **kwargs):
        """Execute a function through the circuit breaker.

        Args:
            func: Async function to protect.
            *args, **kwargs: Function arguments.

        Returns:
            Result from the function.

        Raises:
            CircuitBreakerOpenError: Circuit is open, calls are rejected.
        """
        self._check_state_transition()

        if self._state == "OPEN":
            raise CircuitBreakerOpenError(
                f"Circuit breaker is OPEN. Ollama service unavailable. "
                f"Will retry in {self._time_until_half_open():.0f}s."
            )

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _check_state_transition(self):
        """Check if we should transition from OPEN to HALF_OPEN."""
        if self._state == "OPEN" and self._last_failure_time:
            elapsed = time.time() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                logger.info(
                    "circuit_breaker_half_open",
                    recovery_timeout=self.recovery_timeout,
                )
                self._state = "HALF_OPEN"
                self._half_open_calls = 0

    def _on_success(self):
        """Handle a successful call."""
        if self._state == "HALF_OPEN":
            logger.info("circuit_breaker_closed", message="Recovery confirmed")
        self._state = "CLOSED"
        self._failure_count = 0
        self._half_open_calls = 0

    def _on_failure(self):
        """Handle a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == "HALF_OPEN":
            logger.warning("circuit_breaker_reopened", message="Half-open test failed")
            self._state = "OPEN"
        elif self._failure_count >= self.failure_threshold:
            logger.error(
                "circuit_breaker_opened",
                failure_count=self._failure_count,
                threshold=self.failure_threshold,
            )
            self._state = "OPEN"

    def _time_until_half_open(self) -> float:
        """Seconds until the circuit breaker transitions to HALF_OPEN."""
        if self._last_failure_time is None:
            return 0
        elapsed = time.time() - self._last_failure_time
        return max(0, self.recovery_timeout - elapsed)

    def reset(self):
        """Manually reset the circuit breaker to CLOSED."""
        self._state = "CLOSED"
        self._failure_count = 0
        self._last_failure_time = None
        self._half_open_calls = 0
        logger.info("circuit_breaker_reset")
