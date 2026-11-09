"""Simulator-backed fleet, with all points admitted through the GT06 parser."""

from collections.abc import Mapping

from telematics.clock import Clock
from telematics.codecs.gt06 import GT06Codec
from telematics.ingest.pipeline import IngestPipeline
from telematics.ingest.tap import EventTap
from telematics.models.telemetry import TelemetryPoint
from telematics.simulator.generator import Simulator
from telematics.store.memory import MemoryPointStore


class SimulatorBackend:
    """In-memory fleet backend initialized from deterministic wire frames."""

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
        pipeline = IngestPipeline(GT06Codec(), self._store, clock=clock, event_tap=self.event_tap)
        frames = Simulator(seed=seed, clock=clock, profile_mix=profile_mix).frames(
            vehicles=vehicles
        )
        for vehicle_id, frame in frames:
            pipeline.ingest(vehicle_id, frame)
        self._vehicle_ids = tuple(vehicle_id for vehicle_id, _ in frames)

    def list_vehicle_ids(self) -> tuple[str, ...]:
        return self._vehicle_ids

    def get_points(self, vehicle_id: str) -> tuple[TelemetryPoint, ...]:
        return tuple(self._store.points(vehicle_id))
