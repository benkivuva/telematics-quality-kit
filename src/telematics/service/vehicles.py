"""Vehicle query use case and quality assembly, independent of MCP and I/O."""

from dataclasses import dataclass
from datetime import datetime

from telematics.backends.base import FleetBackend
from telematics.config import FreshnessConfig
from telematics.models.quality import Verdict
from telematics.models.telemetry import TelemetryPoint
from telematics.quality.freshness import FreshnessCheck
from telematics.quality.scoring import score_checks

_LABELS = {Verdict.PASS: "trust it", Verdict.WARN: "be careful", Verdict.BLOCK: "don't trust it"}


@dataclass(frozen=True, slots=True)
class DataQuality:
    verdict: Verdict
    label: str
    trust_score: float
    usable_for_decision: bool
    caveats: tuple[str, ...]
    check_name: str
    check_score: float
    age_seconds: int


@dataclass(frozen=True, slots=True)
class VehicleSummary:
    vehicle_id: str
    latest: TelemetryPoint
    data_quality: DataQuality


class VehicleService:
    """Read fleet points and evaluate freshness at a caller-provided time."""

    def __init__(self, backend: FleetBackend, config: FreshnessConfig) -> None:
        self._backend = backend
        self._freshness = FreshnessCheck(config)

    def list_vehicles(self, *, as_of: datetime, limit: int = 100) -> tuple[VehicleSummary, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        results: list[VehicleSummary] = []
        for vehicle_id in self._backend.list_vehicle_ids()[:limit]:
            points = self._backend.get_points(vehicle_id)
            check = self._freshness.evaluate(points, as_of=as_of)
            verdict = check.verdict
            age = int(check.metric["age_seconds"])
            caveats = (
                (f"Location is {age} seconds old; do not present it as current.",)
                if verdict is not Verdict.PASS
                else ()
            )
            quality = DataQuality(
                verdict=verdict,
                label=_LABELS[verdict],
                trust_score=score_checks((check,)),
                usable_for_decision=verdict is not Verdict.BLOCK,
                caveats=caveats,
                check_name=check.name,
                check_score=check.score,
                age_seconds=age,
            )
            results.append(
                VehicleSummary(vehicle_id, max(points, key=lambda p: p.device_time), quality)
            )
        return tuple(results)
