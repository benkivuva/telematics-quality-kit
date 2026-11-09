"""Pure structural and clock plausibility evaluation."""

from collections.abc import Sequence
from datetime import datetime

from telematics.config import PlausibilityConfig
from telematics.models.quality import CheckResult, Verdict
from telematics.models.telemetry import TelemetryPoint
from telematics.quality._common import result


class PlausibilityCheck:
    """Detect impossible coordinates, timestamps, and speeds."""

    def __init__(self, config: PlausibilityConfig) -> None:
        self._config = config

    def evaluate(
        self,
        points: Sequence[TelemetryPoint],
        *,
        as_of: datetime,
        max_speed_kph: float,
    ) -> CheckResult:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("evaluation time must be timezone-aware")
        if max_speed_kph <= 0:
            raise ValueError("profile maximum speed must be positive")
        invalid = future = excessive_speed = 0
        max_skew = 0.0
        for point in points:
            if point.device_time.tzinfo is None or point.device_time.utcoffset() is None:
                raise ValueError("device time must be timezone-aware")
            if (
                not -90 <= point.latitude <= 90
                or not -180 <= point.longitude <= 180
                or (point.latitude == 0 and point.longitude == 0)
            ):
                invalid += 1
            if point.device_time > as_of:
                future += 1
            if point.speed_kph > max_speed_kph:
                excessive_speed += 1
            reference = point.received_at or as_of
            skew = abs((point.device_time - reference).total_seconds())
            max_skew = max(max_skew, skew)
        if invalid or future or excessive_speed or max_skew > self._config.block_clock_skew_seconds:
            verdict = Verdict.BLOCK
        elif max_skew > self._config.warn_clock_skew_seconds:
            verdict = Verdict.WARN
        else:
            verdict = Verdict.PASS
        return result(
            "plausibility",
            verdict,
            invalid_points=invalid,
            future_points=future,
            excessive_speed_points=excessive_speed,
            max_clock_skew_seconds=max_skew,
        )
