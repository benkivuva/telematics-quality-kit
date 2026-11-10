"""Simulator-backed fleet, with all points admitted through the GT06 parser."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from math import sin, tau
from threading import RLock
from typing import Literal

from telematics.clock import Clock
from telematics.codecs.base import Codec
from telematics.codecs.gt06 import GT06Codec
from telematics.codecs.teltonika import TeltonikaCodec
from telematics.ingest.events import FaultCleared, FaultInjected
from telematics.ingest.pipeline import IngestPipeline
from telematics.ingest.tap import EventTap
from telematics.models.telemetry import TelemetryPoint
from telematics.simulator.generator import Simulator
from telematics.simulator.profiles import VehicleProfile
from telematics.store.memory import MemoryPointStore


@dataclass(frozen=True, slots=True)
class ActiveFault:
    """One simulator-only fault and its optional simulated-time expiry."""

    vehicle_id: str
    name: str
    params: Mapping[str, int | float | str]
    expires_at: datetime | None


class SimulatorBackend:
    """In-memory fleet backend initialized through each profile's wire codec."""

    def __init__(
        self,
        *,
        seed: int,
        clock: Clock,
        vehicles: int,
        profile_mix: Mapping[str, int] | None = None,
        event_tap: EventTap | None = None,
    ) -> None:
        self._lock = RLock()
        self._store = MemoryPointStore()
        self._clock = clock
        self.event_tap = event_tap if event_tap is not None else EventTap()
        simulator = Simulator(seed=seed, clock=clock, profile_mix=profile_mix)
        self._simulator = simulator
        fleet = simulator.vehicles(vehicles=vehicles)
        profile_by_vehicle = {vehicle.vehicle_id: vehicle.profile for vehicle in fleet}
        self._profiles = profile_by_vehicle
        codecs: dict[str, Codec] = {"gt06": GT06Codec(), "teltonika": TeltonikaCodec()}
        pipelines = {
            protocol: IngestPipeline(codec, self._store, clock=clock, event_tap=self.event_tap)
            for protocol, codec in codecs.items()
        }
        frames = simulator.frames(vehicles=vehicles)
        initial_received_at = clock.now()
        self._base_frames = [
            (vehicle_id, frame, initial_received_at) for vehicle_id, frame in frames
        ]
        self._frames = dict(frames)
        self._protocol_by_vehicle = {
            vehicle_id: profile_by_vehicle[vehicle_id].protocol for vehicle_id, _ in frames
        }
        self._codecs = codecs
        self._active_faults: dict[str, ActiveFault] = {}
        self._next_fault_id = 1
        self._tick_index = 0
        initial_time = clock.now()
        self._next_tick = {
            vehicle_id: initial_time + timedelta(seconds=profile.report_interval_seconds)
            for vehicle_id, profile in profile_by_vehicle.items()
        }
        for vehicle_id, frame in frames:
            profile = profile_by_vehicle[vehicle_id]
            pipelines[profile.protocol].ingest(vehicle_id, frame)
        self._vehicle_ids = tuple(vehicle_id for vehicle_id, _ in frames)

    def list_vehicle_ids(self) -> tuple[str, ...]:
        return self._vehicle_ids

    def get_points(self, vehicle_id: str) -> tuple[TelemetryPoint, ...]:
        with self._lock:
            return tuple(self._store.points(vehicle_id))

    def advance(self, duration: timedelta) -> datetime:
        """Advance simulated time and ingest deterministic profile-cadence frames."""
        with self._lock:
            return self._advance(duration)

    def _advance(self, duration: timedelta) -> datetime:
        if duration <= timedelta(0):
            raise ValueError("simulator advance duration must be positive")
        advance_clock = getattr(self._clock, "advance", None)
        if not callable(advance_clock):
            raise TypeError("simulator backend requires an advanceable clock")
        end_time = self._clock.now() + duration
        pipelines = {
            name: IngestPipeline(codec, self._store, clock=self._clock, event_tap=self.event_tap)
            for name, codec in self._codecs.items()
        }
        while self._next_tick and min(self._next_tick.values()) <= end_time:
            tick_at = min(self._next_tick.values())
            advance_clock(tick_at - self._clock.now())
            if self._expire_faults():
                pipelines = self._pipelines()
            self._tick_index += 1
            frames_at = dict(
                self._simulator.frames_at(
                    vehicles=len(self._vehicle_ids), at=tick_at, tick_index=self._tick_index
                )
            )
            due = [vehicle for vehicle, next_at in self._next_tick.items() if next_at == tick_at]
            for vehicle_id in due:
                self._next_tick[vehicle_id] += timedelta(
                    seconds=self._profiles[vehicle_id].report_interval_seconds
                )
                frame = frames_at[vehicle_id]
                if any(
                    active.vehicle_id == vehicle_id and active.name == "rural_blackout"
                    for active in self._active_faults.values()
                ):
                    continue
                self._base_frames.append((vehicle_id, frame, tick_at))
                self._frames[vehicle_id] = frame
                self._ingest_faulted(pipelines, vehicle_id, frame)
        advance_clock(end_time - self._clock.now())
        self._expire_faults()
        return end_time

    def get_profile(self, vehicle_id: str) -> VehicleProfile:
        return self._profiles[vehicle_id]

    def faults(self) -> "SimulatorBackend":
        """Expose simulator-only fault operations as an optional capability."""
        return self

    def inject_fault(
        self,
        vehicle_id: str,
        fault: Literal[
            "stale_device",
            "gps_drift",
            "rural_blackout",
            "duplicate_heartbeats",
            "ignition_flicker",
            "clock_skew",
            "fuel_sensor_spike",
            "buffered_burst",
        ],
        params: Mapping[str, int | float | str],
    ) -> tuple[str, str]:
        """Apply a reversible simulator fault before frames enter their parser."""
        with self._lock:
            return self._inject_fault(vehicle_id, fault, params)

    def _inject_fault(
        self,
        vehicle_id: str,
        fault: Literal[
            "stale_device",
            "gps_drift",
            "rural_blackout",
            "duplicate_heartbeats",
            "ignition_flicker",
            "clock_skew",
            "fuel_sensor_spike",
            "buffered_burst",
        ],
        params: Mapping[str, int | float | str],
    ) -> tuple[str, str]:
        if vehicle_id not in self._frames:
            raise ValueError(f"unknown simulator vehicle {vehicle_id}")
        self._severity_multiplier(params)
        expires_at = None
        duration_value = params.get("duration")
        if duration_value is not None:
            if not isinstance(duration_value, str):
                raise ValueError("fault duration must be an integer followed by s, m, or h")
            expires_at = self._clock.now() + self._parse_duration(duration_value)
        fault_id = f"fault-{self._next_fault_id:04d}"
        self._next_fault_id += 1
        self._active_faults[fault_id] = ActiveFault(vehicle_id, fault, dict(params), expires_at)
        self._rebuild_store()
        impact = {
            "stale_device": "freshness BLOCK at high severity (device time shifted by 20m)",
            "gps_drift": "drift BLOCK within 2m at high severity (implausible consecutive fixes)",
            "rural_blackout": "freshness BLOCK after 5m without reports",
            "duplicate_heartbeats": "duplicates BLOCK when duplicate fraction reaches its threshold",
            "ignition_flicker": "ignition WARN when repeated transitions exceed its window threshold",
            "clock_skew": "plausibility BLOCK at high severity (device clock shifted by 20m)",
            "fuel_sensor_spike": "fuel WARN when the unexplained drop threshold is crossed",
            "buffered_burst": "duplicates flags repeated records in the buffered burst",
        }[fault]
        self.event_tap.publish(FaultInjected(vehicle_id, fault, impact))
        return fault_id, impact

    def reset_simulator(self, *, fault: str | None = None, vehicle_id: str | None = None) -> int:
        """Clear matching simulator faults and restore original encoded frames."""
        with self._lock:
            return self._reset_simulator(fault=fault, vehicle_id=vehicle_id)

    def _reset_simulator(self, *, fault: str | None = None, vehicle_id: str | None = None) -> int:
        selected = tuple(
            (fault_id, active)
            for fault_id, active in self._active_faults.items()
            if (fault is None or active.name == fault)
            and (vehicle_id is None or active.vehicle_id == vehicle_id)
        )
        for fault_id, active in selected:
            del self._active_faults[fault_id]
            self.event_tap.publish(FaultCleared(active.vehicle_id, active.name))
        if selected:
            self._rebuild_store()
        return len(selected)

    def _expire_faults(self) -> bool:
        """Remove faults whose injected-clock duration has elapsed."""
        now = self._clock.now()
        expired = [
            (fault_id, active)
            for fault_id, active in self._active_faults.items()
            if active.expires_at is not None and active.expires_at <= now
        ]
        if expired:
            for fault_id, active in expired:
                del self._active_faults[fault_id]
                self.event_tap.publish(FaultCleared(active.vehicle_id, active.name))
            self._rebuild_store()
        return bool(expired)

    def _pipelines(self) -> dict[str, IngestPipeline]:
        """Create protocol pipelines targeting the current memory store."""
        return {
            name: IngestPipeline(codec, self._store, clock=self._clock, event_tap=self.event_tap)
            for name, codec in self._codecs.items()
        }

    @staticmethod
    def _parse_duration(value: str) -> timedelta:
        """Parse a positive simulated duration ending in s, m, or h."""
        if len(value) < 2 or not value[:-1].isdigit() or int(value[:-1]) <= 0:
            raise ValueError("fault duration must be a positive integer followed by s, m, or h")
        multiplier = {"s": 1, "m": 60, "h": 3600}.get(value[-1])
        if multiplier is None:
            raise ValueError("fault duration must end in s, m, or h")
        return timedelta(seconds=int(value[:-1]) * multiplier)

    def _rebuild_store(self) -> None:
        self._store = MemoryPointStore()
        pipelines = {
            name: IngestPipeline(codec, self._store, clock=self._clock, event_tap=self.event_tap)
            for name, codec in self._codecs.items()
        }
        active_by_vehicle: dict[str, list[tuple[str, Mapping[str, int | float | str]]]] = {}
        for active in self._active_faults.values():
            active_by_vehicle.setdefault(active.vehicle_id, []).append((active.name, active.params))
        for vehicle_id, frame, received_at in self._base_frames:
            self._ingest_faulted(
                pipelines,
                vehicle_id,
                frame,
                [
                    (fault, params)
                    for fault, params in active_by_vehicle.get(vehicle_id, [])
                    if fault != "rural_blackout"
                ],
                received_at=received_at,
            )

    def _ingest_faulted(
        self,
        pipelines: Mapping[str, IngestPipeline],
        vehicle_id: str,
        frame: bytes,
        faults: list[tuple[str, Mapping[str, int | float | str]]] | None = None,
        *,
        received_at: datetime | None = None,
    ) -> None:
        protocol = self._protocol_by_vehicle[vehicle_id]
        codec = self._codecs[protocol]
        points = codec.decode(frame)
        for fault, params in faults if faults is not None else self._faults_for(vehicle_id):
            points = [self._apply_fault(point, fault, params) for point in points]
            if fault == "duplicate_heartbeats":
                repeats = round(2 * self._severity_multiplier(params))
                points = [*points, *(points * repeats)]
            elif fault == "buffered_burst":
                points.reverse()
        for point in points:
            pipelines[protocol].ingest(vehicle_id, codec.encode((point,)), received_at=received_at)

    def _faults_for(self, vehicle_id: str) -> list[tuple[str, Mapping[str, int | float | str]]]:
        return [
            (active.name, active.params)
            for active in self._active_faults.values()
            if active.vehicle_id == vehicle_id
        ]

    @staticmethod
    def _apply_fault(
        point: TelemetryPoint, fault: str, params: Mapping[str, int | float | str]
    ) -> TelemetryPoint:
        multiplier = SimulatorBackend._severity_multiplier(params)
        if fault in {"stale_device", "clock_skew"}:
            duration = timedelta(minutes=10 * multiplier)
            return replace(point, device_time=point.device_time - duration)
        if fault == "gps_drift":
            # Deterministic per-fix jitter that varies between consecutive fixes,
            # so the drift check sees impossible movement without teleporting.
            phase = point.device_time.timestamp() / 47.0 * tau
            offset = sin(phase) * 0.02 * multiplier
            return replace(point, latitude=min(89.9, max(-89.9, point.latitude + offset)))
        if fault == "ignition_flicker":
            return replace(point, ignition_on=not bool(point.ignition_on))
        if fault == "fuel_sensor_spike":
            return replace(point, fuel_level_percent=100.0)
        return point

    @staticmethod
    def _severity_multiplier(params: Mapping[str, int | float | str]) -> float:
        # Phase 5 severity deliberately scales the fault's default magnitude/duration.
        severity = params.get("severity", "medium")
        multipliers = {"low": 0.5, "medium": 1.0, "high": 2.0}
        if not isinstance(severity, str) or severity not in multipliers:
            raise ValueError("severity must be low, medium, or high")
        return multipliers[severity]
