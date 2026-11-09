"""Vehicle queries and full quality assembly, independent of MCP and I/O."""

from collections.abc import Mapping
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
from telematics.models.quality import CheckResult, Verdict
from telematics.models.telemetry import TelemetryPoint
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

    def reset_simulator(self) -> int: ...


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


@dataclass(frozen=True, slots=True)
class VehicleSummary:
    vehicle_id: str
    latest: TelemetryPoint
    points: tuple[TelemetryPoint, ...]
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


class VehicleService:
    """Read backend telemetry and evaluate its six v0.1 quality checks."""

    def __init__(self, backend: FleetBackend, config: FreshnessConfig) -> None:
        self._backend = backend
        self._freshness = FreshnessCheck(config)
        self._config = config
        self._drift = DriftCheck(DriftConfig())
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
        verdict = max(
            (check.verdict for check in checks), key=lambda value: list(Verdict).index(value)
        )
        freshness = checks[0]
        age = int(freshness.metric["age_seconds"])
        caveats = tuple(
            f"{check.name} check returned {check.verdict.value}."
            for check in checks
            if check.verdict is not Verdict.PASS
        )
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

    def get_points(self, vehicle_id: str) -> tuple[TelemetryPoint, ...]:
        return self._backend.get_points(vehicle_id)

    def fault_capability(self) -> FaultOperations | None:
        capability_method = getattr(self._backend, "faults", None)
        if not callable(capability_method):
            return None
        return cast(FaultOperations, capability_method())

    def fleet_trust_score(self, *, as_of: datetime) -> float:
        summaries = self.list_vehicles(as_of=as_of, limit=200)
        return (
            sum(item.data_quality.trust_score for item in summaries) / len(summaries)
            if summaries
            else 1.0
        )
