"""Explicit UTC clock dependencies for deterministic InvestSystem runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from .canonical import normalize_utc


@runtime_checkable
class Clock(Protocol):
    """Small clock contract injected at run identity boundaries."""

    def now(self) -> datetime:
        """Return the current instant as an aware UTC ``datetime``."""

        ...


class SystemClock:
    """Production clock backed by the host system's UTC clock."""

    __slots__ = ()

    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class FixedClock:
    """Deterministic clock that always returns one validated UTC instant."""

    instant: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "instant", normalize_utc(self.instant, field_name="instant"))

    def now(self) -> datetime:
        return self.instant


def read_clock(clock: Clock, *, field_name: str = "clock.now()") -> datetime:
    """Read and validate an injected clock, rejecting naive or non-UTC results."""

    return normalize_utc(clock.now(), field_name=field_name)
