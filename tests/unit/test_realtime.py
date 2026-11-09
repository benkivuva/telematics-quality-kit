"""Deterministic checks for simulator speed scaling."""

from datetime import UTC, datetime, timedelta

import pytest

from telematics.backends.simulator import SimulatorBackend
from telematics.clock import ManualClock
from telematics.simulator.realtime import SimulatorClockDriver


@pytest.mark.unit
@pytest.mark.parametrize(
    ("elapsed", "speed", "expected"), [(1.0, 1.0, 1), (1.0, 60.0, 60), (2.5, 4.0, 10)]
)
def test_speed_driver_scales_elapsed_time_on_the_injected_clock(
    elapsed: float, speed: float, expected: int
) -> None:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    clock = ManualClock(start)
    backend = SimulatorBackend(seed=42, clock=clock, vehicles=1)
    driver = SimulatorClockDriver(backend, speed=speed)

    end = driver.advance_elapsed(elapsed)

    assert end == start + timedelta(seconds=expected)
    assert clock.now() == end
    assert len(backend.get_points("TRK-0001")) == expected // 30 + 1


@pytest.mark.unit
def test_speed_driver_rejects_nonpositive_speed() -> None:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    backend = SimulatorBackend(seed=42, clock=ManualClock(start), vehicles=1)

    with pytest.raises(ValueError, match="speed must be positive"):
        SimulatorClockDriver(backend, speed=0)
