"""Circuit breaker for stage executions.

State machine (Phase 0-3-c):
  closed     - normal operation
  open       - reject all calls until cooldown elapses
  half_open  - allow exactly one trial; success -> closed, failure -> open

We deliberately keep the breaker in-process and time-driven via a
`now()` callable so tests can advance time without sleeping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal

import time

State = Literal["closed", "open", "half_open"]


class BreakerOpen(RuntimeError):
    """Raised by `guard()` when the breaker is open or no probe slot is available."""


@dataclass
class CircuitBreaker:
    failure_threshold: int
    cooldown_sec: float
    name: str = "default"
    now: Callable[[], float] = field(default=time.monotonic)

    def __post_init__(self) -> None:
        self._state: State = "closed"
        self._failures = 0
        self._opened_at: float | None = None
        self._half_open_in_flight = False

    @property
    def state(self) -> State:
        # Lazy promotion: once cooldown has elapsed we move to half_open the
        # next time someone observes the state, so callers don't need to poll.
        if (
            self._state == "open"
            and self._opened_at is not None
            and self.now() - self._opened_at >= self.cooldown_sec
        ):
            self._state = "half_open"
            self._half_open_in_flight = False
        return self._state

    def guard(self) -> None:
        """Call before invoking the protected operation.

        Raises `BreakerOpen` if the call should be rejected.
        """
        if self.state == "open":
            raise BreakerOpen(f"{self.name}: breaker open")
        if self.state == "half_open":
            if self._half_open_in_flight:
                # One probe at a time. Subsequent callers see open until the
                # probe finishes.
                raise BreakerOpen(f"{self.name}: breaker half_open probe in flight")
            self._half_open_in_flight = True

    def record_success(self) -> None:
        """Call after the protected operation succeeded."""
        if self._state == "half_open":
            # Probe passed — back to normal.
            self._state = "closed"
        self._failures = 0
        self._half_open_in_flight = False
        self._opened_at = None

    def record_failure(self) -> None:
        """Call after the protected operation failed."""
        if self._state == "half_open":
            self._trip()
            return
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._trip()

    def _trip(self) -> None:
        self._state = "open"
        self._opened_at = self.now()
        self._half_open_in_flight = False
