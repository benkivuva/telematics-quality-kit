"""Pure unexplained fuel-level change evaluation."""

from collections.abc import Sequence

from telematics.config import FuelConfig
from telematics.models.quality import CheckResult, Verdict
from telematics.models.telemetry import TelemetryPoint
from telematics.quality._common import result


class FuelCheck:
    """Flag fuel drops that travel and ignition do not explain."""

    def __init__(self, config: FuelConfig) -> None:
        self._config = config

    def evaluate(self, points: Sequence[TelemetryPoint], *, distance_km: float) -> CheckResult:
        measured = [point for point in points if point.fuel_level_percent is not None]
        unexplained_drop = 0.0
        ignition_on = any(point.ignition_on is True for point in points)
        if len(measured) >= 2:
            unexplained_drop = float(measured[0].fuel_level_percent or 0) - float(
                measured[-1].fuel_level_percent or 0
            )
        flagged = (
            ignition_on
            and unexplained_drop > self._config.unexplained_drop_percent
            and distance_km < self._config.max_distance_km
        )
        return result(
            "fuel",
            Verdict.WARN if flagged else Verdict.PASS,
            unexplained_drop=max(0.0, unexplained_drop) if flagged else 0.0,
            measured_points=len(measured),
            distance_km=distance_km,
        )
