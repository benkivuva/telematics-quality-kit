"""Normalized telemetry values shared by protocol codecs."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class TelemetryPoint:
    """One decoded GPS point with UTC device time and protocol precision."""

    device_time: datetime
    latitude: float
    longitude: float
    speed_kph: float
    course_deg: int
    satellites: int
    serial_number: int
    received_at: datetime | None = None
    out_of_order: bool = False
    ignition_on: bool | None = None
    fuel_level_percent: float | None = None
