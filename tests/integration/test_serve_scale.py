"""The serve CLI starts an MCP process that lists the requested fleet size."""

import asyncio
import sys
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from telematics.mcp.schemas import ListVehiclesOutput


@pytest.mark.integration
def test_serve_cli_exposes_200_vehicles_over_mcp() -> None:
    asyncio.run(_assert_serve_lists_two_hundred())


async def _assert_serve_lists_two_hundred() -> None:
    project_root = Path(__file__).parents[2]
    server_code = (
        "from telematics.cli.main import main; "
        "main(['serve', '--vehicles', '200', '--transport', 'stdio'])"
    )
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-c", server_code],
        cwd=project_root,
    )

    async with (
        stdio_client(parameters) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as client,
    ):
        await client.initialize()
        result = await client.call_tool("list_vehicles", {"limit": 200})

    payload = ListVehiclesOutput.model_validate(result.structured_content)
    assert len(payload.vehicles) == 200
    assert all(vehicle.data_quality for vehicle in payload.vehicles)
