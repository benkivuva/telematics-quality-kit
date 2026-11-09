"""Freshness verdict boundary tests using explicit simulated timestamps."""

from datetime import UTC, datetime, timedelta

import pytest

from telematics.config import FreshnessConfig
from telematics.models.quality import Verdict
from telematics.models.telemetry import TelemetryPoint
from telematics.quality.freshness import FreshnessCheck

_AS_OF = datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)


def point_at_age(age_seconds: int) -> TelemetryPoint:
    return TelemetryPoint(
        device_time=_AS_OF - timedelta(seconds=age_seconds),
        latitude=12.5,
        longitude=-45.25,
        speed_kph=18.0,
        course_deg=123,
        satellites=8,
        serial_number=7,
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("age_seconds", "expected_verdict", "expected_score"),
    [
        (59, Verdict.PASS, 1.0),
        (60, Verdict.PASS, 1.0),
        (61, Verdict.WARN, 0.79),
        (299, Verdict.WARN, 0.79),
        (300, Verdict.WARN, 0.79),
        (301, Verdict.BLOCK, 0.39),
    ],
)
def test_freshness_threshold_boundaries(
    age_seconds: int,
    expected_verdict: Verdict,
    expected_score: float,
) -> None:
    result = FreshnessCheck(FreshnessConfig()).evaluate(
        (point_at_age(age_seconds),),
        as_of=_AS_OF,
    )

    assert result.verdict is expected_verdict
    assert result.score == expected_score
    assert result.metric["age_seconds"] == age_seconds
    assert result.metric["expected_interval_seconds"] == 30
