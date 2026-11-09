"""Simulator-backed fleet, with all points admitted through the GT06 parser."""

from telematics.clock import Clock
from telematics.codecs.gt06 import GT06Codec
from telematics.ingest.pipeline import IngestPipeline
from telematics.models.telemetry import TelemetryPoint
from telematics.simulator.generator import Simulator
from telematics.store.memory import MemoryPointStore


class SimulatorBackend:
    """In-memory fleet backend initialized from deterministic wire frames."""

    def __init__(self, *, seed: int, clock: Clock, vehicles: int) -> None:
        self._store = MemoryPointStore()
        pipeline = IngestPipeline(GT06Codec(), self._store)
        for vehicle_id, frame in Simulator(seed=seed, clock=clock).frames(vehicles=vehicles):
            pipeline.ingest(vehicle_id, frame)
        self._vehicle_ids = tuple(f"TRK-{index:04d}" for index in range(1, vehicles + 1))

    def list_vehicle_ids(self) -> tuple[str, ...]:
        return self._vehicle_ids

    def get_points(self, vehicle_id: str) -> tuple[TelemetryPoint, ...]:
        return tuple(self._store.points(vehicle_id))
