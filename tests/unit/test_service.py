"""Service layer quality assembly tests."""

from datetime import UTC, datetime

import pytest

from telematics.backends.simulator import SimulatorBackend
from telematics.clock import ManualClock
from telematics.config import FreshnessConfig
from telematics.service.vehicles import VehicleService


@pytest.mark.unit
def test_vehicle_service_returns_freshness_quality_for_each_vehicle() -> None:
    now = datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)
    backend = SimulatorBackend(seed=1, clock=ManualClock(now), vehicles=2)

    vehicles = VehicleService(backend, FreshnessConfig()).list_vehicles(as_of=now)

    assert len(vehicles) == 2
    assert all(vehicle.data_quality.trust_score == 1.0 for vehicle in vehicles)
    assert all(vehicle.data_quality.label == "trust it" for vehicle in vehicles)
