"""In-process MCP contract test for list_vehicles."""

import asyncio
from datetime import UTC, datetime

import anyio
import pytest
from mcp.client.session import ClientSession
from mcp.shared.memory import create_client_server_memory_streams

from telematics.backends.simulator import SimulatorBackend
from telematics.clock import ManualClock
from telematics.config import FreshnessConfig
from telematics.mcp.schemas import ListVehiclesOutput
from telematics.mcp.server import create_server
from telematics.service.vehicles import VehicleService


@pytest.mark.integration
def test_list_vehicles_returns_valid_quality_blocks() -> None:
    asyncio.run(_assert_list_vehicles())


async def _assert_list_vehicles() -> None:
    now = datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)
    service = VehicleService(
        SimulatorBackend(seed=7, clock=ManualClock(now), vehicles=2), FreshnessConfig()
    )
    server = create_server(service, as_of=now)

    async with create_client_server_memory_streams() as (client_streams, server_streams):
        client_read, client_write = client_streams
        server_read, server_write = server_streams
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(
                server._lowlevel_server.run,
                server_read,
                server_write,
                server._lowlevel_server.create_initialization_options(),
            )
            async with ClientSession(client_read, client_write) as client:
                await client.initialize()
                result = await client.call_tool("list_vehicles", {"limit": 10})
            task_group.cancel_scope.cancel()

    payload = ListVehiclesOutput.model_validate(result.structured_content)
    assert len(payload.vehicles) == 2
    assert all(vehicle.data_quality.verdict == "PASS" for vehicle in payload.vehicles)
