"""Simulator-backed fleet, with all points admitted through the GT06 parser."""

from collections.abc import Mapping

from telematics.clock import Clock
from telematics.codecs.base import Codec
from telematics.codecs.gt06 import GT06Codec
from telematics.codecs.teltonika import TeltonikaCodec
from telematics.ingest.pipeline import IngestPipeline
from telematics.ingest.tap import EventTap
from telematics.models.telemetry import TelemetryPoint
from telematics.simulator.generator import Simulator
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
        self.event_tap = event_tap if event_tap is not None else EventTap()
        simulator = Simulator(seed=seed, clock=clock, profile_mix=profile_mix)
        fleet = simulator.vehicles(vehicles=vehicles)
        profile_by_vehicle = {vehicle.vehicle_id: vehicle.profile for vehicle in fleet}
        codecs: dict[str, Codec] = {"gt06": GT06Codec(), "teltonika": TeltonikaCodec()}
        pipelines = {
            protocol: IngestPipeline(codec, self._store, clock=clock, event_tap=self.event_tap)
            for protocol, codec in codecs.items()
        }
        frames = simulator.frames(vehicles=vehicles)
        for vehicle_id, frame in frames:
            profile = profile_by_vehicle[vehicle_id]
            pipelines[profile.protocol].ingest(vehicle_id, frame)
        self._vehicle_ids = tuple(vehicle_id for vehicle_id, _ in frames)

    def list_vehicle_ids(self) -> tuple[str, ...]:
        return self._vehicle_ids

    def get_points(self, vehicle_id: str) -> tuple[TelemetryPoint, ...]:
        return tuple(self._store.points(vehicle_id))
