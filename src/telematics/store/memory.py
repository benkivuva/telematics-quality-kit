"""In-memory point storage for the embedded simulator."""

from datetime import timedelta

from telematics.models.telemetry import TelemetryPoint


class MemoryPointStore:
    """Append-only point store with per-vehicle histories."""

    def __init__(
        self,
        *,
        retention: timedelta = timedelta(hours=1),
        max_points_per_vehicle: int = 10_000,
    ) -> None:
        if retention <= timedelta(0):
            raise ValueError("retention must be positive")
        if max_points_per_vehicle < 1:
            raise ValueError("per-vehicle point limit must be positive")
        self._retention = retention
        self._max_points_per_vehicle = max_points_per_vehicle
        self._points: dict[str, list[TelemetryPoint]] = {}

    def append(self, vehicle_id: str, point: TelemetryPoint) -> None:
        if point.received_at is not None and (
            point.received_at.tzinfo is None or point.received_at.utcoffset() is None
        ):
            raise ValueError("receive time must be timezone-aware")
        vehicle_points = self._points.setdefault(vehicle_id, [])
        vehicle_points.append(point)
        if point.received_at is not None:
            cutoff = point.received_at - self._retention
            vehicle_points[:] = [
                stored
                for stored in vehicle_points
                if stored.received_at is None or stored.received_at >= cutoff
            ]
        if len(vehicle_points) > self._max_points_per_vehicle:
            del vehicle_points[: len(vehicle_points) - self._max_points_per_vehicle]

    def points(self, vehicle_id: str) -> tuple[TelemetryPoint, ...]:
        return tuple(self._points.get(vehicle_id, ()))

    def latest(self, vehicle_id: str) -> TelemetryPoint | None:
        points = self._points.get(vehicle_id)
        return points[-1] if points else None
