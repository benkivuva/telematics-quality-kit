"""Pure movement drift evaluation."""

from collections.abc import Sequence
from itertools import pairwise
from math import asin, cos, radians, sin, sqrt

from telematics.config import DriftConfig
from telematics.models.quality import CheckResult
from telematics.models.telemetry import TelemetryPoint
from telematics.quality._common import fraction_verdict, result


def _distance_meters(first: TelemetryPoint, second: TelemetryPoint) -> float:
    lat1, lat2 = radians(first.latitude), radians(second.latitude)
    dlat = lat2 - lat1
    dlon = radians(second.longitude - first.longitude)
    value = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6_371_000 * 2 * asin(sqrt(value))


class DriftCheck:
    """Flag impossible jumps and stationary GPS jitter."""

    def __init__(self, config: DriftConfig) -> None:
        self._config = config

    def evaluate(self, points: Sequence[TelemetryPoint], *, max_speed_kph: float) -> CheckResult:
        if max_speed_kph <= 0:
            raise ValueError("profile maximum speed must be positive")
        ordered = sorted(points, key=lambda point: point.device_time)
        flagged: set[int] = set()
        for index, (first, second) in enumerate(pairwise(ordered), start=1):
            elapsed = (second.device_time - first.device_time).total_seconds()
            if elapsed <= 0:
                continue
            distance = _distance_meters(first, second)
            implied_speed = distance / elapsed * 3.6
            if implied_speed > max_speed_kph or (
                second.speed_kph == 0 and distance > self._config.stationary_jitter_meters
            ):
                flagged.add(index)
        fraction = len(flagged) / len(ordered) if ordered else 0.0
        return result(
            "drift",
            fraction_verdict(fraction, self._config.warn_fraction, self._config.block_fraction),
            flagged_points=len(flagged),
            total_points=len(ordered),
            flagged_fraction=fraction,
        )
