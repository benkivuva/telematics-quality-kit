"""Ignition debounce and transition episode tests."""

from datetime import UTC, datetime, timedelta

import pytest

from telematics.config import IgnitionConfig
from telematics.models.quality import Verdict
from telematics.models.telemetry import TelemetryPoint
from telematics.quality.ignition import IgnitionCheck


def point(second: int, ignition: bool) -> TelemetryPoint:
    return TelemetryPoint(
        datetime(2025, 1, 1, tzinfo=UTC) + timedelta(seconds=second),
        1.0,
        2.0,
        0.0,
        0,
        8,
        second,
        ignition_on=ignition,
    )


@pytest.mark.unit
def test_ignition_warns_for_one_debounced_chatter_episode() -> None:
    points = tuple(point(i * 10, bool(i % 2)) for i in range(7))

    result = IgnitionCheck(IgnitionConfig()).evaluate(points)

    assert result.verdict is Verdict.WARN
    assert result.metric["episodes"] == 1


@pytest.mark.unit
def test_ignition_blocks_for_three_chatter_episodes() -> None:
    points = tuple(
        point(episode * 400 + transition * 10, bool(transition % 2))
        for episode in range(3)
        for transition in range(7)
    )

    result = IgnitionCheck(IgnitionConfig()).evaluate(points)

    assert result.verdict is Verdict.BLOCK
    assert result.metric["episodes"] >= 3
