"""Simulator-backed fleet, with all points admitted through the GT06 parser."""

from collections.abc import Mapping
from dataclasses import replace
from typing import Literal

from telematics.clock import Clock
from telematics.codecs.base import Codec
from telematics.codecs.gt06 import GT06Codec
from telematics.codecs.teltonika import TeltonikaCodec
from telematics.ingest.pipeline import IngestPipeline
from telematics.ingest.tap import EventTap
from telematics.models.telemetry import TelemetryPoint
from telematics.simulator.generator import Simulator
from telematics.simulator.profiles import VehicleProfile
from telematics.store.memory import MemoryPointStore


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
        self._store = MemoryPointStore()
        self._clock = clock
        self.event_tap = event_tap if event_tap is not None else EventTap()
        simulator = Simulator(seed=seed, clock=clock, profile_mix=profile_mix)
        fleet = simulator.vehicles(vehicles=vehicles)
        profile_by_vehicle = {vehicle.vehicle_id: vehicle.profile for vehicle in fleet}
        self._profiles = profile_by_vehicle
        codecs: dict[str, Codec] = {"gt06": GT06Codec(), "teltonika": TeltonikaCodec()}
        pipelines = {
            protocol: IngestPipeline(codec, self._store, clock=clock, event_tap=self.event_tap)
            for protocol, codec in codecs.items()
        }
        frames = simulator.frames(vehicles=vehicles)
        self._frames = dict(frames)
        self._protocol_by_vehicle = {
            vehicle_id: profile_by_vehicle[vehicle_id].protocol for vehicle_id, _ in frames
        }
        self._codecs = codecs
        self._active_faults: dict[str, tuple[str, str, Mapping[str, int | float | str]]] = {}
        self._next_fault_id = 1
        for vehicle_id, frame in frames:
            profile = profile_by_vehicle[vehicle_id]
            pipelines[profile.protocol].ingest(vehicle_id, frame)
        self._vehicle_ids = tuple(vehicle_id for vehicle_id, _ in frames)

    def list_vehicle_ids(self) -> tuple[str, ...]:
        return self._vehicle_ids

    def get_points(self, vehicle_id: str) -> tuple[TelemetryPoint, ...]:
        return tuple(self._store.points(vehicle_id))

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
        if vehicle_id not in self._frames:
            raise ValueError(f"unknown simulator vehicle {vehicle_id}")
        fault_id = f"fault-{self._next_fault_id:04d}"
        self._next_fault_id += 1
        self._active_faults[fault_id] = (vehicle_id, fault, dict(params))
        self._rebuild_store()
        impact = {
            "stale_device": "freshness degrades",
            "gps_drift": "drift plausibility degrades",
            "rural_blackout": "freshness degrades",
            "duplicate_heartbeats": "duplicate rate increases",
            "ignition_flicker": "ignition transitions increase",
            "clock_skew": "plausibility degrades",
            "fuel_sensor_spike": "fuel sensor quality degrades",
            "buffered_burst": "duplicate and ordering checks are exercised",
        }[fault]
        return fault_id, impact

    def reset_simulator(self) -> int:
        """Clear simulator faults and restore original encoded frames."""
        cleared = len(self._active_faults)
        self._active_faults.clear()
        self._rebuild_store()
        return cleared

    def _rebuild_store(self) -> None:
        self._store = MemoryPointStore()
        pipelines = {
            name: IngestPipeline(codec, self._store, clock=self._clock, event_tap=self.event_tap)
            for name, codec in self._codecs.items()
        }
        active_by_vehicle: dict[str, list[str]] = {}
        for vehicle_id, fault, _params in self._active_faults.values():
            active_by_vehicle.setdefault(vehicle_id, []).append(fault)
        for vehicle_id, frame in self._frames.items():
            protocol = self._protocol_by_vehicle[vehicle_id]
            codec = self._codecs[protocol]
            points = codec.decode(frame)
            for fault in active_by_vehicle.get(vehicle_id, []):
                points = [self._apply_fault(point, fault) for point in points]
                if fault == "duplicate_heartbeats":
                    points = [*points, *points]
                elif fault == "buffered_burst":
                    points.reverse()
            for point in points:
                pipelines[protocol].ingest(vehicle_id, codec.encode((point,)))

    @staticmethod
    def _apply_fault(point: TelemetryPoint, fault: str) -> TelemetryPoint:
        if fault in {"stale_device", "rural_blackout", "clock_skew"}:
            from datetime import timedelta

            return replace(point, device_time=point.device_time - timedelta(minutes=10))
        if fault == "gps_drift":
            return replace(point, latitude=min(89.9, point.latitude + 0.1))
        if fault == "ignition_flicker":
            return replace(point, ignition_on=not bool(point.ignition_on))
        if fault == "fuel_sensor_spike":
            return replace(point, fuel_level_percent=100.0)
        return point
