from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from invest_system import Clock, FixedClock, SystemClock, read_clock


class NaiveClock:
    def now(self) -> datetime:
        return datetime(2026, 7, 30, 8, 0, 0)


class NonUtcClock:
    def now(self) -> datetime:
        return datetime(2026, 7, 30, 16, 0, 0, tzinfo=timezone(timedelta(hours=8)))


def test_fixed_clock_is_an_explicit_deterministic_utc_dependency() -> None:
    instant = datetime(2026, 7, 30, 8, 0, 0, 123, tzinfo=UTC)
    clock = FixedClock(instant)
    first = read_clock(clock)
    second = read_clock(clock)

    assert isinstance(clock, Clock)
    assert first == second == instant


def test_system_clock_returns_validated_utc() -> None:
    clock = SystemClock()
    instant = read_clock(clock)

    assert isinstance(clock, Clock)
    assert instant.tzinfo is UTC
    assert instant.utcoffset() == timedelta(0)


@pytest.mark.parametrize("clock", [NaiveClock(), NonUtcClock()])
def test_read_clock_fails_closed_for_naive_or_non_utc_implementations(clock: Clock) -> None:
    with pytest.raises(ValueError):
        read_clock(clock)


@pytest.mark.parametrize(
    "instant",
    [
        datetime(2026, 7, 30, 8, 0, 0),
        datetime(2026, 7, 30, 16, 0, 0, tzinfo=timezone(timedelta(hours=8))),
    ],
)
def test_fixed_clock_rejects_naive_or_non_utc_instants(instant: datetime) -> None:
    with pytest.raises(ValueError):
        FixedClock(instant)
