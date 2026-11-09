"""In-memory point storage for the embedded simulator."""

from telematics.models.telemetry import TelemetryPoint


class MemoryPointStore:
    """Append-only point store with per-vehicle histories."""

    def __init__(self) -> None:
        self._points: dict[str, list[TelemetryPoint]] = {}

    def append(self, vehicle_id: str, point: TelemetryPoint) -> None:
        self._points.setdefault(vehicle_id, []).append(point)

    def points(self, vehicle_id: str) -> tuple[TelemetryPoint, ...]:
        return tuple(self._points.get(vehicle_id, ()))

    def latest(self, vehicle_id: str) -> TelemetryPoint | None:
        points = self._points.get(vehicle_id)
        return points[-1] if points else None
