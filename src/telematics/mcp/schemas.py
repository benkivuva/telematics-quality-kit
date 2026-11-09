"""Validated Pydantic models for the Phase 2 MCP query contract."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DataQualityOutput(StrictModel):
    verdict: str
    label: str
    trust_score: float
    usable_for_decision: bool
    caveats: list[str]


class VehicleOutput(StrictModel):
    vehicle_id: str
    device_time: datetime
    latitude: float
    longitude: float
    speed_kph: float
    data_quality: DataQualityOutput


class ListVehiclesInput(StrictModel):
    limit: int = 100


class ListVehiclesOutput(StrictModel):
    schema_version: str = "1.0"
    vehicles: list[VehicleOutput]
