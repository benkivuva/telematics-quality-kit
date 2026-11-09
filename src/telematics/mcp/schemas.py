"""Strict Pydantic schemas for the v0.1 MCP contract."""

from datetime import datetime
from typing import Literal

from mcp.server.mcpserver.utilities.func_metadata import ArgModelBase
from pydantic import ConfigDict, Field, model_validator


class StrictModel(ArgModelBase):
    """Base model forbidding fields outside the public contract."""

    model_config = ConfigDict(extra="forbid")


class DataQualityOutput(StrictModel):
    verdict: Literal["PASS", "WARN", "BLOCK"]
    label: Literal["trust it", "be careful", "don't trust it"]
    symbol: Literal["✓", "⚠", "⛔"]
    trust_score: float = Field(ge=0, le=1)
    usable_for_decision: bool
    caveats: list[str]
    withheld: list[str] = Field(default_factory=list)
    checks: list["CheckOutput"] = Field(default_factory=list)
    as_of: datetime
    window: "WindowOutput"


class CheckOutput(StrictModel):
    name: str
    verdict: Literal["PASS", "WARN", "BLOCK"]
    score: float = Field(ge=0, le=1)
    metric: dict[str, int | float | str]


class VehicleOutput(StrictModel):
    vehicle_id: str
    device_time: datetime
    latitude: float
    longitude: float
    speed_kph: float
    data_quality: DataQualityOutput


class WindowInput(StrictModel):
    start: datetime | None = None
    end: datetime | None = None
    last: str | None = None

    @model_validator(mode="after")
    def validate_window(self) -> "WindowInput":
        if self.start is not None or self.end is not None:
            if self.last is not None:
                raise ValueError("provide last or start/end, not both")
            if self.start is None or self.end is None:
                raise ValueError("provide both start and end")
            if any(
                value.tzinfo is None or value.utcoffset() is None
                for value in (self.start, self.end)
            ):
                raise ValueError("window timestamps must be timezone-aware")
            if self.start >= self.end:
                raise ValueError("provide an increasing start/end window")
            return self
        if self.last is not None:
            if not self.last.endswith(("m", "h", "d")) or not self.last[:-1].isdigit():
                raise ValueError("last must be a positive duration such as 24h")
            if int(self.last[:-1]) <= 0:
                raise ValueError("last duration must be positive")
            return self
        return self


class WindowOutput(StrictModel):
    start: datetime
    end: datetime


class ListVehiclesInput(StrictModel):
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = None


class VehicleIdInput(StrictModel):
    vehicle_id: str


class TripHistoryInput(VehicleIdInput, WindowInput):
    pass


class FuelEventsInput(WindowInput):
    vehicle_id: str | None = None


class QualityReportInput(StrictModel):
    vehicle_id: str | None = None
    verbose: bool = False


class FleetFreshnessInput(StrictModel):
    pass


class DriftReportInput(VehicleIdInput, WindowInput):
    pass


class DuplicatesReportInput(WindowInput):
    pass


class QualityIssuesInput(StrictModel):
    min_verdict: Literal["WARN", "BLOCK"] = "WARN"


FaultName = Literal[
    "stale_device",
    "gps_drift",
    "rural_blackout",
    "duplicate_heartbeats",
    "ignition_flicker",
    "clock_skew",
    "fuel_sensor_spike",
    "buffered_burst",
]


class InjectFaultInput(VehicleIdInput):
    fault: FaultName
    params: dict[str, int | float | str] = Field(default_factory=dict)


class ResetSimulatorInput(StrictModel):
    pass


class ListVehiclesOutput(StrictModel):
    schema_version: str = "1.0"
    vehicles: list[VehicleOutput]
    next_cursor: str | None = None


class ToolErrorOutput(StrictModel):
    schema_version: str = "1.0"
    error: dict[str, str]


class VehicleLocationOutput(StrictModel):
    schema_version: str = "1.0"
    vehicle_id: str
    device_time: datetime
    latitude: float | None
    longitude: float | None
    speed_kph: float | None
    age_seconds: int
    data_quality: DataQualityOutput


class TripOutput(StrictModel):
    start: datetime
    end: datetime
    distance_km: float | None
    withheld: list[str] = Field(default_factory=list)


class TripHistoryOutput(StrictModel):
    schema_version: str = "1.0"
    vehicle_id: str
    trips: list[TripOutput]
    data_quality: DataQualityOutput


class FuelEventOutput(StrictModel):
    vehicle_id: str
    device_time: datetime
    drop_percent: float
    quality_flag: str


class FuelEventsOutput(StrictModel):
    schema_version: str = "1.0"
    events: list[FuelEventOutput]
    data_quality: DataQualityOutput


class QualityReportOutput(StrictModel):
    schema_version: str = "1.0"
    vehicle_id: str | None
    fleet_trust_score: float
    vehicles: list[VehicleOutput]


class FleetFreshnessVehicleOutput(StrictModel):
    vehicle_id: str
    age_seconds: int
    verdict: Literal["PASS", "WARN", "BLOCK"]


class FleetFreshnessOutput(StrictModel):
    schema_version: str = "1.0"
    fleet_trust_score: float
    vehicles: list[FleetFreshnessVehicleOutput]
    data_quality: DataQualityOutput


class DriftReportOutput(StrictModel):
    schema_version: str = "1.0"
    vehicle_id: str
    verdict: Literal["PASS", "WARN", "BLOCK"]
    flagged_points: int
    total_points: int
    flagged_fraction: float
    data_quality: DataQualityOutput


class DuplicatesReportOutput(StrictModel):
    schema_version: str = "1.0"
    duplicate_count: int
    duplicate_fraction: float
    heartbeat_rate_ratio: float
    verdict: Literal["PASS", "WARN", "BLOCK"]
    data_quality: DataQualityOutput


class QualityIssueOutput(StrictModel):
    vehicle_id: str
    check: str
    verdict: Literal["WARN", "BLOCK"]
    score: float
    suggested_next_check: str


class QualityIssuesOutput(StrictModel):
    schema_version: str = "1.0"
    issues: list[QualityIssueOutput]
    data_quality: DataQualityOutput


class FaultInjectionOutput(StrictModel):
    schema_version: str = "1.0"
    fault_id: str
    vehicle_id: str
    fault: FaultName
    expected_quality_impact: str
    data_quality: DataQualityOutput


class ResetSimulatorOutput(StrictModel):
    schema_version: str = "1.0"
    reset: bool
    cleared_faults: int
    data_quality: DataQualityOutput


INPUT_MODELS = (
    ListVehiclesInput,
    VehicleIdInput,
    TripHistoryInput,
    FuelEventsInput,
    QualityReportInput,
    FleetFreshnessInput,
    DriftReportInput,
    DuplicatesReportInput,
    QualityIssuesInput,
    InjectFaultInput,
    ResetSimulatorInput,
)

TOOL_INPUT_MODELS: dict[str, type[StrictModel]] = {
    "list_vehicles": ListVehiclesInput,
    "get_vehicle_location": VehicleIdInput,
    "get_trip_history": TripHistoryInput,
    "get_fuel_events": FuelEventsInput,
    "get_quality_report": QualityReportInput,
    "check_fleet_freshness": FleetFreshnessInput,
    "check_gps_drift": DriftReportInput,
    "check_duplicates": DuplicatesReportInput,
    "list_quality_issues": QualityIssuesInput,
    "inject_fault": InjectFaultInput,
    "reset_simulator": ResetSimulatorInput,
}

TOOL_OUTPUT_MODELS: dict[str, type[StrictModel]] = {
    "list_vehicles": ListVehiclesOutput,
    "get_vehicle_location": VehicleLocationOutput,
    "get_trip_history": TripHistoryOutput,
    "get_fuel_events": FuelEventsOutput,
    "get_quality_report": QualityReportOutput,
    "check_fleet_freshness": FleetFreshnessOutput,
    "check_gps_drift": DriftReportOutput,
    "check_duplicates": DuplicatesReportOutput,
    "list_quality_issues": QualityIssuesOutput,
    "inject_fault": FaultInjectionOutput,
    "reset_simulator": ResetSimulatorOutput,
}
