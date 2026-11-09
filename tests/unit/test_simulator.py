"""Deterministic synthetic byte generation tests."""

from datetime import UTC, datetime

import pytest

from telematics.clock import ManualClock
from telematics.simulator.generator import Simulator


@pytest.mark.unit
def test_same_seed_and_clock_generate_identical_frames() -> None:
    now = datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)
    first = Simulator(seed=42, clock=ManualClock(now)).frames(vehicles=2)
    second = Simulator(seed=42, clock=ManualClock(now)).frames(vehicles=2)

    assert first == second
    assert [vehicle_id for vehicle_id, _ in first] == ["TRK-0001", "TRK-0002"]
