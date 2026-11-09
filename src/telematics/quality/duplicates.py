"""Pure duplicate and heartbeat-rate evaluation."""

from collections import Counter
from collections.abc import Sequence

from telematics.config import DuplicatesConfig
from telematics.models.quality import CheckResult, Verdict
from telematics.models.telemetry import TelemetryPoint
from telematics.quality._common import fraction_verdict, result


class DuplicatesCheck:
    """Detect repeated position records and excessive reporting rates."""

    def __init__(self, config: DuplicatesConfig) -> None:
        self._config = config

    def evaluate(
        self, points: Sequence[TelemetryPoint], *, expected_interval_seconds: int
    ) -> CheckResult:
        if expected_interval_seconds <= 0:
            raise ValueError("expected reporting interval must be positive")
        keys = [(point.device_time, point.latitude, point.longitude) for point in points]
        counts = Counter(keys)
        duplicate_count = sum(count - 1 for count in counts.values())
        fraction = duplicate_count / len(points) if points else 0.0
        ordered = sorted(points, key=lambda point: point.device_time)
        elapsed = (
            (ordered[-1].device_time - ordered[0].device_time).total_seconds()
            if len(ordered) > 1
            else 0
        )
        observed_interval = elapsed / (len(ordered) - 1) if len(ordered) > 1 else float("inf")
        rate_ratio = expected_interval_seconds / observed_interval if observed_interval > 0 else 0.0
        verdict = fraction_verdict(
            fraction, self._config.warn_fraction, self._config.block_fraction
        )
        if rate_ratio > self._config.heartbeat_rate_ratio:
            verdict = Verdict.BLOCK
        return result(
            "duplicates",
            verdict,
            duplicate_count=duplicate_count,
            duplicate_fraction=fraction,
            heartbeat_rate_ratio=rate_ratio,
        )
