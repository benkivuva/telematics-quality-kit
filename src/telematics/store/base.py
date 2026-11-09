"""Storage boundary for decoded telemetry points."""

from collections.abc import Sequence
from typing import Protocol

from telematics.models.telemetry import TelemetryPoint


class PointStore(Protocol):
    """Append-only point storage used by ingestion and services."""

    def append(self, vehicle_id: str, point: TelemetryPoint) -> None: ...

    def points(self, vehicle_id: str) -> Sequence[TelemetryPoint]: ...

    def latest(self, vehicle_id: str) -> TelemetryPoint | None: ...
