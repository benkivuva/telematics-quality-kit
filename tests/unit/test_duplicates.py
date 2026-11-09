"""Duplicate and heartbeat storm threshold tests."""

from datetime import UTC, datetime, timedelta

import pytest

from telematics.config import DuplicatesConfig
from telematics.models.quality import Verdict
from telematics.models.telemetry import TelemetryPoint
from telematics.quality.duplicates import DuplicatesCheck


def point(second: int, serial: int) -> TelemetryPoint:
    return TelemetryPoint(
        datetime(2025, 1, 1, tzinfo=UTC) + timedelta(seconds=second), 1.0, 2.0, 0.0, 0, 8, serial
    )


@pytest.mark.unit
def test_duplicates_warn_at_five_percent_repeated_records() -> None:
    points = tuple(point(i * 30, i) for i in range(19)) + (point(0, 20),)

    result = DuplicatesCheck(DuplicatesConfig()).evaluate(points, expected_interval_seconds=30)

    assert result.verdict is Verdict.WARN
    assert result.metric["duplicate_count"] == 1


@pytest.mark.unit
def test_duplicates_block_on_heartbeat_storm() -> None:
    points = tuple(point(i, i) for i in range(10))

    result = DuplicatesCheck(DuplicatesConfig()).evaluate(points, expected_interval_seconds=30)

    assert result.verdict is Verdict.BLOCK
    assert result.metric["heartbeat_rate_ratio"] > 3
