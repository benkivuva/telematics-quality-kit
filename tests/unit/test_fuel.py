"""Fuel sensor heuristic tests."""

from datetime import UTC, datetime, timedelta

import pytest

from telematics.config import FuelConfig
from telematics.models.quality import Verdict
from telematics.models.telemetry import TelemetryPoint
from telematics.quality.fuel import FuelCheck


def point(minutes: int, level: float, *, ignition: bool = True) -> TelemetryPoint:
    return TelemetryPoint(
        datetime(2025, 1, 1, tzinfo=UTC) + timedelta(minutes=minutes),
        1.0,
        2.0,
        0.0,
        0,
        8,
        minutes,
        ignition_on=ignition,
        fuel_level_percent=level,
    )


@pytest.mark.unit
def test_fuel_flags_unexplained_drop_when_ignition_on_and_distance_low() -> None:
    result = FuelCheck(FuelConfig()).evaluate((point(0, 80), point(1, 60)), distance_km=0.1)

    assert result.verdict is Verdict.WARN
    assert result.metric["unexplained_drop"] == 20


@pytest.mark.unit
def test_fuel_does_not_flag_drop_without_ignition() -> None:
    result = FuelCheck(FuelConfig()).evaluate(
        (point(0, 80, ignition=False), point(1, 50, ignition=False)), distance_km=0
    )

    assert result.verdict is Verdict.PASS
