"""MCP v2 server wiring for the vertical slice."""

from datetime import datetime

from mcp.server.mcpserver import MCPServer

from telematics.mcp.schemas import DataQualityOutput, ListVehiclesOutput, VehicleOutput
from telematics.service.vehicles import VehicleService


def create_server(service: VehicleService, *, as_of: datetime) -> MCPServer:
    """Build an MCP server exposing the read-only list_vehicles tool."""
    server = MCPServer(name="telematics-quality-kit", version="0.1.0")

    @server.tool(
        name="list_vehicles",
        description="List synthetic vehicles with a freshness trust verdict and caveats.",
        structured_output=True,
    )
    def list_vehicles(limit: int = 100) -> ListVehiclesOutput:
        """Return a bounded list of vehicles and their data quality."""
        summaries = service.list_vehicles(as_of=as_of, limit=limit)
        return ListVehiclesOutput(
            vehicles=[
                VehicleOutput(
                    vehicle_id=vehicle.vehicle_id,
                    device_time=vehicle.latest.device_time,
                    latitude=vehicle.latest.latitude,
                    longitude=vehicle.latest.longitude,
                    speed_kph=vehicle.latest.speed_kph,
                    data_quality=DataQualityOutput(
                        verdict=vehicle.data_quality.verdict.value,
                        label=vehicle.data_quality.label,
                        trust_score=vehicle.data_quality.trust_score,
                        usable_for_decision=vehicle.data_quality.usable_for_decision,
                        caveats=list(vehicle.data_quality.caveats),
                    ),
                )
                for vehicle in summaries
            ]
        )

    return server
