"""Service layer quality assembly tests."""

from datetime import UTC, datetime

import pytest

from telematics.backends.simulator import SimulatorBackend
from telematics.clock import ManualClock
from telematics.config import FreshnessConfig
from telematics.models.quality import Verdict
from telematics.service.vehicles import VehicleService, fleet_data_quality


@pytest.mark.unit
def test_vehicle_service_returns_freshness_quality_for_each_vehicle() -> None:
    now = datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)
    backend = SimulatorBackend(seed=1, clock=ManualClock(now), vehicles=2)

    vehicles = VehicleService(backend, FreshnessConfig()).list_vehicles(as_of=now)

    assert len(vehicles) == 2
    assert all(vehicle.data_quality.trust_score == 1.0 for vehicle in vehicles)
    assert all(vehicle.data_quality.label == "trust it" for vehicle in vehicles)


@pytest.mark.unit
def test_fleet_data_quality_is_the_worst_vehicle_verdict() -> None:
    now = datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)
    backend = SimulatorBackend(seed=1, clock=ManualClock(now), vehicles=2)
    backend.inject_fault("LRY-0001", "stale_device", {"severity": "high"})
    service = VehicleService(backend, FreshnessConfig())

    fleet = service.evaluate_fleet(as_of=now)

    assert fleet.data_quality.verdict is Verdict.BLOCK
    assert fleet.data_quality.usable_for_decision is False
    assert fleet.data_quality.blocked_vehicles == ("LRY-0001",)
    assert fleet.data_quality.blocked_vehicle_count == 1
    assert fleet.data_quality.trust_score > 0.5
    assert any("LRY-0001" in caveat for caveat in fleet.data_quality.caveats)


@pytest.mark.unit
def test_fleet_data_quality_rejects_an_empty_fleet() -> None:
    with pytest.raises(ValueError, match="no vehicles"):
        fleet_data_quality(())
