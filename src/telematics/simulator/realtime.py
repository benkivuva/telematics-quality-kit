"""Realtime driver that scales wall-clock elapsed time into simulator time."""

import time
from collections.abc import Callable
from datetime import datetime, timedelta
from threading import Event

from telematics.backends.simulator import SimulatorBackend


class SimulatorClockDriver:
    """Advance an embedded simulator at a configurable multiple of real time."""

    def __init__(
        self,
        backend: SimulatorBackend,
        *,
        speed: float,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if speed <= 0:
            raise ValueError("speed must be positive")
        self._backend = backend
        self._speed = speed
        self._monotonic = monotonic

    def advance_elapsed(self, elapsed_seconds: float) -> datetime:
        """Advance by elapsed wall time multiplied by configured simulator speed."""
        if elapsed_seconds < 0:
            raise ValueError("elapsed time cannot be negative")
        return self._backend.advance(timedelta(seconds=elapsed_seconds * self._speed))

    def run(self, stop: Event) -> None:
        """Advance in short real-time intervals until the serving process stops."""
        previous = self._monotonic()
        while not stop.wait(0.1):
            current = self._monotonic()
            elapsed = current - previous
            previous = current
            if elapsed > 0:
                self.advance_elapsed(elapsed)
