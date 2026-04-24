"""Tests for the CircuitBreaker.

Time is injected so we never sleep — each test moves the clock manually
to verify the closed -> open -> half_open -> closed/open transitions.
"""

import pytest

from app.pipeline.breaker import BreakerOpen, CircuitBreaker


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def _make(failure_threshold: int = 3, cooldown_sec: float = 60.0) -> tuple[CircuitBreaker, _Clock]:
    clock = _Clock()
    return CircuitBreaker(failure_threshold=failure_threshold, cooldown_sec=cooldown_sec, now=clock), clock


def test_starts_closed_and_allows_calls():
    cb, _ = _make()
    cb.guard()
    cb.record_success()
    assert cb.state == "closed"


def test_trips_after_threshold_failures():
    cb, _ = _make(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "closed"
    cb.record_failure()
    assert cb.state == "open"


def test_open_rejects_calls():
    cb, _ = _make(failure_threshold=1)
    cb.record_failure()
    assert cb.state == "open"
    with pytest.raises(BreakerOpen):
        cb.guard()


def test_cooldown_elapses_to_half_open():
    cb, clock = _make(failure_threshold=1, cooldown_sec=10)
    cb.record_failure()
    clock.t = 9.99
    assert cb.state == "open"
    clock.t = 10.0
    assert cb.state == "half_open"


def test_half_open_probe_success_closes_breaker():
    # Use threshold=3 so we can prove the counter was cleared by success
    # (one subsequent failure must not re-trip the breaker).
    cb, clock = _make(failure_threshold=3, cooldown_sec=10)
    cb.record_failure(); cb.record_failure(); cb.record_failure()
    assert cb.state == "open"
    clock.t = 10
    cb.guard()  # Probe permitted.
    cb.record_success()
    assert cb.state == "closed"
    # Counter was cleared — a single failure here must not trip again.
    cb.record_failure()
    assert cb.state == "closed"


def test_half_open_probe_failure_reopens():
    cb, clock = _make(failure_threshold=2, cooldown_sec=5)
    cb.record_failure(); cb.record_failure()
    assert cb.state == "open"
    clock.t = 5
    cb.guard()
    cb.record_failure()
    assert cb.state == "open"
    # Cooldown restarts from the new opened_at.
    clock.t = 9
    assert cb.state == "open"
    clock.t = 10
    assert cb.state == "half_open"


def test_only_one_probe_at_a_time():
    cb, clock = _make(failure_threshold=1, cooldown_sec=1)
    cb.record_failure()
    clock.t = 1
    cb.guard()  # First probe in flight.
    with pytest.raises(BreakerOpen):
        cb.guard()  # Second caller is rejected.
