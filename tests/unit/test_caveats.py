"""Plain-language caveat tests."""

from datetime import UTC, datetime

import pytest

from telematics.backends.simulator import SimulatorBackend
from telematics.clock import ManualClock
from telematics.config import FreshnessConfig
from telematics.models.quality import CheckResult, Verdict
from telematics.quality.caveats import caveat_for
from telematics.service.vehicles import VehicleService


def _check(name: str, verdict: Verdict, **metric: float) -> CheckResult:
    return CheckResult(name=name, verdict=verdict, score=0.5, metric=metric)


@pytest.mark.unit
def test_pass_checks_have_no_caveat() -> None:
    assert caveat_for(_check("freshness", Verdict.PASS, age_seconds=0)) is None


@pytest.mark.unit
def test_freshness_caveat_is_a_plain_sentence_with_age() -> None:
    caveat = caveat_for(_check("freshness", Verdict.BLOCK, age_seconds=360))

    assert caveat is not None
    assert "6 minutes" in caveat
    assert "do not present it as current" in caveat


@pytest.mark.unit
def test_drift_caveat_reports_the_flagged_percentage() -> None:
    caveat = caveat_for(
        _check("drift", Verdict.BLOCK, flagged_fraction=0.14, flagged_points=7, total_points=50)
    )

    assert caveat is not None
    assert "14%" in caveat
    assert "unreliable" in caveat


@pytest.mark.unit
def test_duplicates_caveat_reports_the_duplicate_share() -> None:
    caveat = caveat_for(
        _check("duplicates", Verdict.WARN, duplicate_fraction=0.1, duplicate_count=3)
    )

    assert caveat is not None
    assert "10%" in caveat


@pytest.mark.unit
def test_ignition_caveat_reports_transitions() -> None:
    caveat = caveat_for(_check("ignition", Verdict.WARN, transitions=5, episodes=1))

    assert caveat is not None
    assert "5" in caveat


@pytest.mark.unit
def test_plausibility_caveat_names_the_structural_problem() -> None:
    caveat = caveat_for(
        _check(
            "plausibility",
            Verdict.BLOCK,
            invalid_points=1,
            future_points=0,
            excessive_speed_points=0,
            max_clock_skew_seconds=0.0,
        )
    )

    assert caveat is not None
    assert "invalid" in caveat


@pytest.mark.unit
def test_fuel_caveat_reports_the_unexplained_drop() -> None:
    caveat = caveat_for(_check("fuel", Verdict.WARN, unexplained_drop=12.5, distance_km=0.4))

    assert caveat is not None
    assert "12%" in caveat


@pytest.mark.unit
def test_service_caveats_are_plain_sentences() -> None:
    now = datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)
    backend = SimulatorBackend(seed=42, clock=ManualClock(now), vehicles=1)
    backend.inject_fault("TRK-0001", "stale_device", {"severity": "high"})

    summary = VehicleService(backend, FreshnessConfig()).evaluate_vehicle("TRK-0001", as_of=now)

    assert summary.data_quality.caveats
    for caveat in summary.data_quality.caveats:
        assert "check returned" not in caveat
    assert any("old" in caveat for caveat in summary.data_quality.caveats)
