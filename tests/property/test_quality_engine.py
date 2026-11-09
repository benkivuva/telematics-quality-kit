"""Quality and simulator fault monotonicity properties."""

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from telematics.backends.simulator import SimulatorBackend
from telematics.clock import ManualClock
from telematics.config import DuplicatesConfig, FreshnessConfig
from telematics.models.telemetry import TelemetryPoint
from telematics.quality.duplicates import DuplicatesCheck
from telematics.service.vehicles import VehicleService


@pytest.mark.property
@given(st.lists(st.integers(min_value=0, max_value=100), min_size=1, max_size=20))
def test_duplicate_evaluation_is_idempotent(seconds: list[int]) -> None:
    origin = datetime(2025, 1, 1, tzinfo=UTC)
    points = tuple(
        TelemetryPoint(origin + timedelta(seconds=value), 1.0, 2.0, 0.0, 0, 8, index)
        for index, value in enumerate(seconds)
    )
    check = DuplicatesCheck(DuplicatesConfig())

    first = check.evaluate(points, expected_interval_seconds=30)
    second = check.evaluate(points, expected_interval_seconds=30)

    assert first == second


@pytest.mark.property
def test_injecting_stale_device_fault_does_not_improve_trust_score() -> None:
    now = datetime(2025, 1, 1, tzinfo=UTC)
    backend = SimulatorBackend(seed=24, clock=ManualClock(now), vehicles=1)
    service = VehicleService(backend, FreshnessConfig())
    before = service.evaluate_vehicle("TRK-0001", as_of=now).data_quality.trust_score

    fault_id, _impact = backend.faults().inject_fault("TRK-0001", "stale_device", {})
    after = service.evaluate_vehicle("TRK-0001", as_of=now).data_quality.trust_score
    backend.faults().reset_simulator()

    assert fault_id == "fault-0001"
    assert after <= before
