import asyncio
import enum
import functools
import random
import time
from typing import Awaitable, Callable, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


class CircuitOpenError(Exception):
    """Raised without calling the protected function while its circuit is open."""

    def __init__(self, name: str, retry_after: float):
        super().__init__(f"Circuit '{name}' is open; retry in {retry_after:.1f}s")
        self.name = name
        self.retry_after = retry_after


class CircuitState(str, enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    CLOSED    -> calls pass; `failure_threshold` consecutive failures open it.
    OPEN      -> calls fail fast with CircuitOpenError for `recovery_timeout` seconds.
    HALF_OPEN -> a single probe call is let through; success closes, failure re-opens.

    State is per process. Not thread-safe (meant for a single event loop).
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int,
        recovery_timeout: float,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._clock = clock
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._probing = False

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def is_open(self) -> bool:
        """True while calls would be rejected (open and cooldown not yet elapsed)."""
        return self._state is CircuitState.OPEN and self._retry_after() > 0

    def _retry_after(self) -> float:
        return max(0.0, self._opened_at + self.recovery_timeout - self._clock())

    def before_call(self) -> None:
        if self._state is CircuitState.OPEN:
            retry_after = self._retry_after()
            if retry_after > 0:
                raise CircuitOpenError(self.name, retry_after)
            self._state = CircuitState.HALF_OPEN
            self._probing = False
        if self._state is CircuitState.HALF_OPEN:
            if self._probing:
                raise CircuitOpenError(self.name, self.recovery_timeout)
            self._probing = True

    def on_success(self) -> None:
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._probing = False

    def on_failure(self) -> None:
        self._failures += 1
        if self._state is CircuitState.HALF_OPEN or self._failures >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = self._clock()
        self._probing = False

    def on_abort(self) -> None:
        """The call was cancelled: says nothing about the service, free the probe slot."""
        self._probing = False


def circuit_breaker(
    *,
    name: str | None = None,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
    expected_exceptions: tuple[type[BaseException], ...] = (Exception,),
    timeout: float | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """
    Decorator guarding an async callable with a circuit breaker.

    Only `expected_exceptions` count as service failures; any other exception means
    the service answered (e.g. a validation error) and counts as success.
    `timeout` bounds each call; the resulting TimeoutError counts as a failure
    when it is listed in `expected_exceptions`.
    The breaker is exposed as `wrapper.breaker` for inspection.
    """

    def decorator(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        breaker = CircuitBreaker(name or fn.__qualname__, failure_threshold, recovery_timeout)

        @functools.wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            breaker.before_call()
            try:
                if timeout is None:
                    result = await fn(*args, **kwargs)
                else:
                    async with asyncio.timeout(timeout):
                        result = await fn(*args, **kwargs)
            except expected_exceptions:
                breaker.on_failure()
                raise
            except Exception:
                breaker.on_success()
                raise
            except BaseException:
                breaker.on_abort()
                raise
            breaker.on_success()
            return result

        wrapper.breaker = breaker  # type: ignore[attr-defined]
        return wrapper

    return decorator


def backoff_delay(attempt: int, base: float, cap: float) -> float:
    """Exponential backoff with equal jitter. `attempt` is 1-based."""
    ceiling = min(cap, base * 2 ** (attempt - 1))
    return ceiling / 2 + random.uniform(0, ceiling / 2)
