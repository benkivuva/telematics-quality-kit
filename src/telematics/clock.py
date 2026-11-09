"""Explicit clocks for deterministic simulation and quality evaluation."""

from datetime import datetime, timedelta
from threading import RLock
from typing import Protocol


class Clock(Protocol):
    """Minimal clock interface consumed by time-sensitive code."""

    def now(self) -> datetime:
        """Return the current timezone-aware instant."""


class ManualClock:
    """A clock whose time advances only when the caller requests it."""

    def __init__(self, current_time: datetime) -> None:
        if current_time.tzinfo is None or current_time.utcoffset() is None:
            raise ValueError("clock time must be timezone-aware")
        self._current_time = current_time
        self._lock = RLock()

    def now(self) -> datetime:
        """Return the currently injected instant."""
        with self._lock:
            return self._current_time

    def advance(self, delta: timedelta) -> datetime:
        """Move the clock forward by a non-negative duration."""
        with self._lock:
            if delta < timedelta(0):
                raise ValueError("manual clock cannot move backwards")
            self._current_time += delta
            return self._current_time
