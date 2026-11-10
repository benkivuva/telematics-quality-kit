"""Deterministic report data assembly through the real simulator codecs."""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, cast

import yaml  # type: ignore[import-untyped]

from telematics.backends.simulator import SimulatorBackend
from telematics.clock import ManualClock
from telematics.config import DriftConfig, FreshnessConfig
from telematics.models.quality import Verdict
from telematics.service.vehicles import VehicleService, VehicleSummary

FaultName = Literal[
    "stale_device",
    "gps_drift",
    "rural_blackout",
    "duplicate_heartbeats",
    "ignition_flicker",
    "clock_skew",
    "fuel_sensor_spike",
    "buffered_burst",
]

_START = datetime(2024, 4, 5, 6, 30, 0, tzinfo=UTC)
_FAULT_NAMES = frozenset(
    {
        "stale_device",
        "gps_drift",
        "rural_blackout",
        "duplicate_heartbeats",
        "ignition_flicker",
        "clock_skew",
        "fuel_sensor_spike",
        "buffered_burst",
    }
)
_ALIASES = {
    "stale": "stale_device",
    "drift": "gps_drift",
    "blackout": "rural_blackout",
    "dupes": "duplicate_heartbeats",
    "flicker": "ignition_flicker",
    "skew": "clock_skew",
    "fuel-spike": "fuel_sensor_spike",
    "burst": "buffered_burst",
}


@dataclass(frozen=True, slots=True)
class FaultSpec:
    """One explicit named fault assigned to a synthetic vehicle."""

    fault: str
    vehicle_id: str
    severity: str = "medium"

    def __post_init__(self) -> None:
        canonical = _ALIASES.get(self.fault, self.fault)
        if canonical not in _FAULT_NAMES:
            raise ValueError(f"unknown fault: {self.fault}")
        if self.severity not in {"low", "medium", "high"}:
            raise ValueError("severity must be low, medium, or high")
        object.__setattr__(self, "fault", canonical)


@dataclass(frozen=True, slots=True)
class ReportVehicle:
    """One report row and its detail card source values."""

    vehicle_id: str
    profile_name: str
    protocol: str
    expected_interval_seconds: int
    summary: VehicleSummary
    active_faults: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReportData:
    """Immutable values used by the static HTML renderer."""

    scenario: str
    seed: int
    start: datetime
    end: datetime
    fleet_trust_score: float
    verdict_counts: Mapping[Verdict, int]
    vehicles: tuple[ReportVehicle, ...]
    faults: tuple[FaultSpec, ...]
    detail: int
    command: str


@dataclass(frozen=True, slots=True)
class ScenarioConfig:
    """Safe-loaded report scenario inputs."""

    name: str
    seed: int
    vehicles: int
    duration: timedelta
    faults: tuple[FaultSpec, ...]
    profile_mix: Mapping[str, int] | None = None


def parse_duration(value: str) -> timedelta:
    """Parse an integer duration followed by s, m, or h."""
    if len(value) < 2 or not value[:-1].isdigit() or int(value[:-1]) <= 0:
        raise ValueError("duration must be a positive integer followed by s, m, or h")
    scale = {"s": 1, "m": 60, "h": 3600}.get(value[-1])
    if scale is None:
        raise ValueError("duration must end in s, m, or h")
    return timedelta(seconds=int(value[:-1]) * scale)


def parse_fault_spec(value: str) -> FaultSpec:
    """Parse ``FAULT:VEHICLE[:SEVERITY]`` including the CLI aliases."""
    parts = value.split(":")
    if len(parts) not in {2, 3} or not parts[0] or not parts[1]:
        raise ValueError("fault must look like FAULT:VEHICLE[:SEVERITY]")
    return FaultSpec(parts[0], parts[1], parts[2] if len(parts) == 3 else "medium")


def load_scenario_file(path: str | Path) -> ScenarioConfig:
    """Load a report scenario using PyYAML's safe loader only."""
    try:
        parsed = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid scenario YAML: {exc}") from exc
    if not isinstance(parsed, dict):
        raise TypeError("scenario must be a YAML mapping")
    name = parsed.get("name", Path(path).stem)
    seed = parsed.get("seed", 42)
    vehicles = parsed.get("vehicles", 12)
    duration_value = parsed.get("duration", "1h")
    faults_value = parsed.get("faults", [])
    mix_value = parsed.get("profile_mix")
    if not isinstance(name, str) or not isinstance(seed, int) or not isinstance(vehicles, int):
        raise TypeError("scenario name, seed, and vehicles have invalid types")
    if not isinstance(duration_value, str) or not isinstance(faults_value, list):
        raise TypeError("scenario duration and faults have invalid types")
    faults: list[FaultSpec] = []
    for item in faults_value:
        if not isinstance(item, dict):
            raise TypeError("each scenario fault must be a mapping")
        fault = item.get("fault")
        vehicle_id = item.get("vehicle_id")
        severity = item.get("severity", "medium")
        if (
            not isinstance(fault, str)
            or not isinstance(vehicle_id, str)
            or not isinstance(severity, str)
        ):
            raise TypeError("scenario faults require text fault, vehicle_id, and severity values")
        faults.append(FaultSpec(fault, vehicle_id, severity))
    profile_mix: dict[str, int] | None = None
    if mix_value is not None:
        if not isinstance(mix_value, dict) or any(
            not isinstance(key, str) or not isinstance(value, int)
            for key, value in mix_value.items()
        ):
            raise ValueError("scenario profile_mix must map profile names to integer percentages")
        profile_mix = mix_value
    return ScenarioConfig(
        name, seed, vehicles, parse_duration(duration_value), tuple(faults), profile_mix
    )


def build_report_data(
    *,
    seed: int = 42,
    vehicles: int = 12,
    duration: timedelta = timedelta(hours=1),
    fault_duration: timedelta = timedelta(minutes=20),
    clean: bool = False,
    faults: tuple[FaultSpec, ...] | None = None,
    scenario_name: str | None = None,
    detail: int = 50,
    profile_mix: Mapping[str, int] | None = None,
    command: str | None = None,
    drift_config: DriftConfig | None = None,
) -> ReportData:
    """Generate a deterministic fleet, apply selected faults, and evaluate it."""
    if duration <= timedelta(0):
        raise ValueError("report duration must be positive")
    if fault_duration <= timedelta(0):
        raise ValueError("fault duration must be positive")
    if not 1 <= detail <= 200:
        raise ValueError("report detail must be between 1 and 200")
    clock = ManualClock(_START)
    backend = SimulatorBackend(
        seed=seed,
        clock=clock,
        vehicles=vehicles,
        profile_mix=profile_mix,
    )
    ids = backend.list_vehicle_ids()
    if clean:
        selected_faults: tuple[FaultSpec, ...] = ()
        scenario = scenario_name or "clean baseline"
    elif faults is None:
        showcase = [FaultSpec("stale_device", ids[0], "medium")]
        drift_vehicle = next((identifier for identifier in ids if identifier != ids[0]), None)
        if drift_vehicle is not None:
            showcase.append(FaultSpec("gps_drift", drift_vehicle, "high"))
        selected_faults = tuple(showcase)
        scenario = scenario_name or "showcase"
    else:
        selected_faults = faults
        scenario = scenario_name or "custom drill"
    active_duration = min(fault_duration, duration)
    fault_start = duration - active_duration
    if selected_faults and fault_start > timedelta(0):
        backend.advance(fault_start)
    by_vehicle: dict[str, list[str]] = {}
    for spec in selected_faults:
        backend.inject_fault(
            spec.vehicle_id, cast(FaultName, spec.fault), {"severity": spec.severity}
        )
        by_vehicle.setdefault(spec.vehicle_id, []).append(spec.fault)
    remaining = active_duration if selected_faults else duration
    if remaining > timedelta(0):
        backend.advance(remaining)
    end = clock.now()
    service = VehicleService(backend, FreshnessConfig(), drift_config=drift_config)
    report_vehicles: list[ReportVehicle] = []
    for identifier in ids:
        summary = service.evaluate_vehicle(identifier, as_of=end)
        profile = backend.get_profile(identifier)
        report_vehicles.append(
            ReportVehicle(
                identifier,
                profile.name,
                profile.protocol,
                profile.report_interval_seconds,
                summary,
                tuple(by_vehicle.get(identifier, ())),
            )
        )
    order = {Verdict.PASS: 0, Verdict.WARN: 1, Verdict.BLOCK: 2}
    report_vehicles.sort(
        key=lambda row: (
            -order[row.summary.data_quality.verdict],
            row.summary.data_quality.trust_score,
            row.vehicle_id,
        )
    )
    counts = Counter(row.summary.data_quality.verdict for row in report_vehicles)
    trust_score = (
        sum(row.summary.data_quality.trust_score for row in report_vehicles) / len(report_vehicles)
        if report_vehicles
        else 1.0
    )
    if command is None:
        command_parts = [
            "telematics report",
            f"--seed {seed}",
            f"--vehicles {vehicles}",
            f"--duration {int(duration.total_seconds())}s",
            f"--fault-duration {int(active_duration.total_seconds())}s",
            f"--detail {detail}",
        ]
        if clean:
            command_parts.append("--clean")
        elif faults is not None:
            command_parts.extend(
                f"--inject {spec.fault}:{spec.vehicle_id}:{spec.severity}"
                for spec in selected_faults
            )
        if profile_mix is not None:
            mix_text = ",".join(f"{key}={value}" for key, value in profile_mix.items())
            command_parts.append(f"--profile-mix {mix_text}")
        command = " ".join(command_parts)
    return ReportData(
        scenario,
        seed,
        _START,
        end,
        trust_score,
        {verdict: counts.get(verdict, 0) for verdict in Verdict},
        tuple(report_vehicles),
        selected_faults,
        detail,
        command,
    )
