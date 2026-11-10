"""Realtime driver that scales wall-clock elapsed time into simulator time."""

import time
from collections.abc import Callable
from datetime import datetime, timedelta
from math import isfinite
from threading import Event, Lock

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
        if not isfinite(speed) or speed <= 0:
            raise ValueError("speed must be a positive finite number")
        self._backend = backend
        self._speed = speed
        self._monotonic = monotonic
        self._paused = False
        self._lock = Lock()

    @property
    def speed(self) -> float:
        with self._lock:
            return self._speed

    @property
    def paused(self) -> bool:
        with self._lock:
            return self._paused

    def set_speed(self, speed: float) -> None:
        """Set the real-time multiplier while the driver is running."""
        if not isfinite(speed) or speed <= 0:
            raise ValueError("speed must be a positive finite number")
        with self._lock:
            self._speed = speed

    def pause(self) -> None:
        """Stop automatic simulated-time advancement."""
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        """Resume automatic simulated-time advancement."""
        with self._lock:
            self._paused = False

    def set_backend(self, backend: SimulatorBackend) -> None:
        """Use a replacement simulator after reseeding an embedded session."""
        with self._lock:
            self._backend = backend

    def advance_elapsed(self, elapsed_seconds: float) -> datetime:
        """Advance by elapsed wall time multiplied by configured simulator speed."""
        if elapsed_seconds < 0:
            raise ValueError("elapsed time cannot be negative")
        with self._lock:
            backend = self._backend
            paused = self._paused
            speed = self._speed
        if paused:
            return backend._clock.now()
        return backend.advance(timedelta(seconds=elapsed_seconds * speed))

    def run(self, stop: Event) -> None:
        """Advance in short real-time intervals until the serving process stops."""
        previous = self._monotonic()
        while not stop.wait(0.1):
            current = self._monotonic()
            elapsed = current - previous
            previous = current
            if elapsed > 0 and not self.paused:
                self.advance_elapsed(elapsed)
