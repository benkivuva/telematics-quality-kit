"""Freshness evaluation over decoded telemetry and an explicit evaluation time."""

from collections.abc import Sequence
from datetime import datetime

from telematics.config import FreshnessConfig
from telematics.models.quality import CheckResult, Verdict
from telematics.models.telemetry import TelemetryPoint

_SCORES = {Verdict.PASS: 1.0, Verdict.WARN: 0.79, Verdict.BLOCK: 0.39}


class FreshnessCheck:
    """Evaluate how old the latest decoded device point is."""

    def __init__(self, config: FreshnessConfig) -> None:
        self._config = config

    def evaluate(self, points: Sequence[TelemetryPoint], *, as_of: datetime) -> CheckResult:
        """Return a freshness result without reading the system clock."""
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("evaluation time must be timezone-aware")
        if not points:
            raise ValueError("freshness requires at least one telemetry point")
        latest = max(points, key=lambda point: point.device_time)
        if latest.device_time.tzinfo is None or latest.device_time.utcoffset() is None:
            raise ValueError("device time must be timezone-aware")
        age = (as_of - latest.device_time).total_seconds()
        if age <= self._config.expected_interval_seconds * self._config.warn_after_intervals:
            verdict = Verdict.PASS
        elif age <= self._config.expected_interval_seconds * self._config.block_after_intervals:
            verdict = Verdict.WARN
        else:
            verdict = Verdict.BLOCK
        return CheckResult(
            name="freshness",
            verdict=verdict,
            score=_SCORES[verdict],
            metric={
                "age_seconds": max(0, int(age)),
                "expected_interval_seconds": self._config.expected_interval_seconds,
            },
        )
