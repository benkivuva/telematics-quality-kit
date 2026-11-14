"""Vehicle queries and full quality assembly, independent of MCP and I/O."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from math import asin, cos, radians, sin, sqrt
from typing import Protocol, cast

from telematics.backends.base import FleetBackend
from telematics.config import (
    DriftConfig,
    DuplicatesConfig,
    FreshnessConfig,
    FuelConfig,
    IgnitionConfig,
    PlausibilityConfig,
)
from telematics.models.quality import CheckResult, Verdict, worst_verdict
from telematics.models.telemetry import TelemetryPoint
from telematics.quality.caveats import caveat_for
from telematics.quality.drift import DriftCheck
from telematics.quality.duplicates import DuplicatesCheck
from telematics.quality.freshness import FreshnessCheck
from telematics.quality.fuel import FuelCheck
from telematics.quality.ignition import IgnitionCheck
from telematics.quality.plausibility import PlausibilityCheck
from telematics.quality.scoring import score_checks

_LABELS = {Verdict.PASS: "trust it", Verdict.WARN: "be careful", Verdict.BLOCK: "don't trust it"}
_SYMBOLS = {Verdict.PASS: "✓", Verdict.WARN: "⚠", Verdict.BLOCK: "⛔"}
_DEFAULT_MAX_SPEED_KPH = 90.0


class FaultOperations(Protocol):
    """Optional mutation capability exposed by simulator backends only."""

    def inject_fault(
        self, vehicle_id: str, fault: str, params: Mapping[str, int | float | str]
    ) -> tuple[str, str]: ...

    def reset_simulator(
        self, *, fault: str | None = None, vehicle_id: str | None = None
    ) -> int: ...


@dataclass(frozen=True, slots=True)
class DataQuality:
    verdict: Verdict
    label: str
    symbol: str
    trust_score: float
    usable_for_decision: bool
    caveats: tuple[str, ...]
    check_name: str
    check_score: float
    age_seconds: int
    checks: tuple[CheckResult, ...]
    withheld: tuple[str, ...]
    blocked_vehicles: tuple[str, ...] = ()
    blocked_vehicle_count: int = 0


@dataclass(frozen=True, slots=True)
class VehicleSummary:
    vehicle_id: str
    latest: TelemetryPoint
    points: tuple[TelemetryPoint, ...]
    data_quality: DataQuality


@dataclass(frozen=True, slots=True)
class FleetSummary:
    """One fleet evaluation: every vehicle and the fleet-level trust signal."""

    vehicles: tuple[VehicleSummary, ...]
    data_quality: DataQuality


def _distance_km(points: tuple[TelemetryPoint, ...]) -> float:
    distance = 0.0
    for first, second in pairwise(points):
        lat1, lat2 = radians(first.latitude), radians(second.latitude)
        dlat = lat2 - lat1
        dlon = radians(second.longitude - first.longitude)
        value = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        distance += 6371 * 2 * asin(sqrt(value))
    return distance


def _fleet_caveats(summaries: Sequence[VehicleSummary]) -> tuple[str, ...]:
    blocked_count = sum(1 for summary in summaries if summary.data_quality.verdict is Verdict.BLOCK)
    caveats: list[str] = []
    if blocked_count:
        caveats.append(
            f"{blocked_count} of {len(summaries)} vehicles are BLOCK; "
            "fleet result is not usable for decisions."
        )
    for level in (Verdict.BLOCK, Verdict.WARN):
        entries = [
            f"{summary.vehicle_id}: {caveat}"
            for summary in summaries
            if summary.data_quality.verdict is level
            for caveat in summary.data_quality.caveats
        ]
        caveats.extend(entries[:5])
        if len(entries) > 5:
            caveats.append(f"and {len(entries) - 5} more {level.value} caveats")
    if blocked_count:
        caveats.append(
            "fleet trust score is an average; one blocked vehicle still blocks the fleet."
        )
    return tuple(caveats)


def fleet_data_quality(summaries: Sequence[VehicleSummary]) -> DataQuality:
    """Build the fleet trust signal from the worst vehicle, never the first."""
    if not summaries:
        raise ValueError("no vehicles")
    verdict = worst_verdict(summary.data_quality.verdict for summary in summaries)
    trust_score = sum(summary.data_quality.trust_score for summary in summaries) / len(summaries)
    blocked = tuple(
        sorted(
            summary.vehicle_id
            for summary in summaries
            if summary.data_quality.verdict is Verdict.BLOCK
        )
    )
    withheld = tuple(
        sorted(
            {
                field
                for summary in summaries
                if summary.data_quality.verdict is Verdict.BLOCK
                for field in summary.data_quality.withheld
            }
        )
    )
    return DataQuality(
        verdict=verdict,
        label=_LABELS[verdict],
        symbol=_SYMBOLS[verdict],
        trust_score=trust_score,
        usable_for_decision=verdict is not Verdict.BLOCK,
        caveats=_fleet_caveats(summaries),
        check_name="fleet",
        check_score=trust_score,
        age_seconds=max(summary.data_quality.age_seconds for summary in summaries),
        checks=(),
        withheld=withheld,
        blocked_vehicles=blocked[:5],
        blocked_vehicle_count=len(blocked),
    )


class VehicleService:
    """Read backend telemetry and evaluate its six v0.1 quality checks."""

    def __init__(
        self,
        backend: FleetBackend,
        config: FreshnessConfig,
        *,
        drift_config: DriftConfig | None = None,
    ) -> None:
        self._backend = backend
        self._freshness = FreshnessCheck(config)
        self._config = config
        self._drift = DriftCheck(drift_config or DriftConfig())
        self._duplicates = DuplicatesCheck(DuplicatesConfig())
        self._ignition = IgnitionCheck(IgnitionConfig())
        self._plausibility = PlausibilityCheck(PlausibilityConfig())
        self._fuel = FuelCheck(FuelConfig())

    def evaluate_vehicle(
        self,
        vehicle_id: str,
        *,
        as_of: datetime,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> VehicleSummary:
        points = self._backend.get_points(vehicle_id)
        if start is not None:
            points = tuple(point for point in points if point.device_time >= start)
        if end is not None:
            points = tuple(point for point in points if point.device_time <= end)
        if not points:
            raise ValueError(f"no telemetry points for vehicle {vehicle_id}")
        ordered = tuple(sorted(points, key=lambda point: point.device_time))
        profile = getattr(self._backend, "get_profile", lambda _vehicle: None)(vehicle_id)
        max_speed = float(profile.max_speed_kph) if profile is not None else _DEFAULT_MAX_SPEED_KPH
        interval = (
            profile.report_interval_seconds
            if profile is not None
            else self._config.expected_interval_seconds
        )
        checks = (
            self._freshness.evaluate(ordered, as_of=as_of),
            self._drift.evaluate(ordered, max_speed_kph=max_speed),
            self._duplicates.evaluate(ordered, expected_interval_seconds=interval),
            self._ignition.evaluate(ordered),
            self._plausibility.evaluate(ordered, as_of=as_of, max_speed_kph=max_speed),
            self._fuel.evaluate(ordered, distance_km=_distance_km(ordered)),
        )
        verdict = worst_verdict(check.verdict for check in checks)
        freshness = next(check for check in checks if check.name == "freshness")
        age = int(freshness.metric["age_seconds"])
        caveats = tuple(caveat for check in checks if (caveat := caveat_for(check)) is not None)
        withheld: tuple[str, ...] = (
            ("trip_distance",)
            if verdict is Verdict.BLOCK
            and any(
                check.verdict is Verdict.BLOCK
                for check in checks
                if check.name in {"drift", "plausibility", "freshness"}
            )
            else ()
        )
        quality = DataQuality(
            verdict=verdict,
            label=_LABELS[verdict],
            symbol=_SYMBOLS[verdict],
            trust_score=score_checks(checks),
            usable_for_decision=verdict is not Verdict.BLOCK,
            caveats=caveats,
            check_name=freshness.name,
            check_score=freshness.score,
            age_seconds=age,
            checks=checks,
            withheld=withheld,
            blocked_vehicles=(),
            blocked_vehicle_count=0,
        )
        return VehicleSummary(vehicle_id, ordered[-1], ordered, quality)

    def list_vehicles(
        self, *, as_of: datetime, limit: int = 50, cursor: str | None = None
    ) -> tuple[VehicleSummary, ...]:
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        ids = self._backend.list_vehicle_ids()
        if cursor is not None:
            try:
                start = ids.index(cursor) + 1
            except ValueError as exc:
                raise ValueError("invalid vehicle cursor") from exc
            ids = ids[start:]
        return tuple(self.evaluate_vehicle(vehicle, as_of=as_of) for vehicle in ids[:limit])

    def list_vehicle_ids(self) -> tuple[str, ...]:
        return self._backend.list_vehicle_ids()

    def evaluate_fleet(
        self,
        *,
        as_of: datetime,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> FleetSummary:
        """Evaluate every vehicle once and assemble the fleet trust signal."""
        vehicles = tuple(
            self.evaluate_vehicle(vehicle_id, as_of=as_of, start=start, end=end)
            for vehicle_id in self.list_vehicle_ids()
        )
        return FleetSummary(vehicles, fleet_data_quality(vehicles))

    def get_points(self, vehicle_id: str) -> tuple[TelemetryPoint, ...]:
        return self._backend.get_points(vehicle_id)

    def fault_capability(self) -> FaultOperations | None:
        capability_method = getattr(self._backend, "faults", None)
        if not callable(capability_method):
            return None
        return cast(FaultOperations, capability_method())

    def fleet_trust_score(self, *, as_of: datetime) -> float:
        return self.evaluate_fleet(as_of=as_of).data_quality.trust_score
