"""Drift check threshold tests."""

from datetime import UTC, datetime, timedelta

import pytest

from telematics.config import DriftConfig
from telematics.models.quality import Verdict
from telematics.models.telemetry import TelemetryPoint
from telematics.quality.drift import DriftCheck


def point(seconds: int, latitude: float, *, speed: float = 0.0) -> TelemetryPoint:
    return TelemetryPoint(
        datetime(2025, 1, 1, tzinfo=UTC) + timedelta(seconds=seconds),
        latitude,
        0.0,
        speed,
        0,
        8,
        seconds,
    )


@pytest.mark.unit
def test_drift_flags_jump_above_profile_speed_limit() -> None:
    points = (point(0, 0.0), point(10, 0.01))

    result = DriftCheck(DriftConfig()).evaluate(points, max_speed_kph=90)

    assert result.verdict is Verdict.BLOCK
    assert result.metric["flagged_points"] >= 1


@pytest.mark.unit
def test_drift_flags_stationary_jitter_and_warns_at_one_percent() -> None:
    points = tuple(point(index, 0.0002 if index == 1 else 0.0) for index in range(200))

    result = DriftCheck(DriftConfig(stationary_jitter_meters=10)).evaluate(points, max_speed_kph=90)

    assert result.verdict is Verdict.WARN
    assert result.metric["flagged_points"] == 2
    assert result.metric["flagged_fraction"] == 0.01
