"""The sole service-facing fleet backend boundary."""

from typing import Protocol

from telematics.models.telemetry import TelemetryPoint


class FleetBackend(Protocol):
    """Read-only fleet capabilities required by the vertical slice."""

    def list_vehicle_ids(self) -> tuple[str, ...]: ...

    def get_points(self, vehicle_id: str) -> tuple[TelemetryPoint, ...]: ...
