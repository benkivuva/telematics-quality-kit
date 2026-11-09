"""Protocol-decoding ingestion path for raw device frames."""

from collections.abc import Sequence
from typing import Protocol

from telematics.models.telemetry import TelemetryPoint
from telematics.store.base import PointStore


class Codec(Protocol):
    """Minimal codec interface consumed by ingestion."""

    def decode(self, frame: bytes) -> list[TelemetryPoint]: ...


class IngestPipeline:
    """Decode frames before making normalized points available to quality checks."""

    def __init__(self, codec: Codec, store: PointStore) -> None:
        self._codec = codec
        self._store = store

    def ingest(self, vehicle_id: str, frame: bytes) -> Sequence[TelemetryPoint]:
        points = self._codec.decode(frame)
        for point in points:
            self._store.append(vehicle_id, point)
        return tuple(points)
