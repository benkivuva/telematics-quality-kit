"""CLI sessions backed by an embedded MCP server or an attached MCP URL."""

import asyncio
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from typing import Any

import anyio
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.mcpserver import MCPServer
from mcp.shared.memory import create_client_server_memory_streams
from mcp.types import TextContent

from telematics.backends.simulator import SimulatorBackend
from telematics.clock import ManualClock
from telematics.config import DriftConfig, FreshnessConfig
from telematics.mcp.server import create_server
from telematics.service.vehicles import VehicleService
from telematics.simulator.realtime import SimulatorClockDriver

ToolCall = Callable[[str, dict[str, Any]], dict[str, Any]]


class MCPToolError(RuntimeError):
    """A connected MCP server rejected a tool request."""


def _root_exception_message(error: BaseException) -> str:
    while isinstance(error, BaseExceptionGroup) and error.exceptions:
        error = error.exceptions[0]
    return str(error)


class EmbeddedSession:
    """A deterministic simulator session using the public in-process MCP tools."""

    def __init__(
        self,
        backend: SimulatorBackend,
        clock: ManualClock,
        service: VehicleService,
        *,
        vehicles: int,
        seed: int,
        profile_mix: dict[str, int] | None,
        drift_config: DriftConfig,
    ) -> None:
        self.backend = backend
        self.clock = clock
        self.service = service
        self.vehicles = vehicles
        self.seed = seed
        self.profile_mix = profile_mix
        self.drift_config = drift_config
        self.clock_driver = SimulatorClockDriver(backend, speed=1.0)
        self.server = create_server(service, as_of=clock.now(), clock=clock)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call the embedded server through the SDK's in-process client."""
        return asyncio.run(_call_memory_server(self.server, name, arguments))

    def list_tools(self) -> list[dict[str, str]]:
        """List the public tools registered by the embedded MCP server."""
        return asyncio.run(_list_memory_tools(self.server))

    def advance(self, duration: timedelta) -> datetime:
        """Advance the shared simulated clock and emit cadence frames."""
        return self.backend.advance(duration)

    def reseed(self, seed: int) -> None:
        """Rebuild the embedded fleet from a new seed at the current sim time."""
        backend = SimulatorBackend(
            seed=seed,
            clock=self.clock,
            vehicles=self.vehicles,
            profile_mix=self.profile_mix,
        )
        service = VehicleService(backend, FreshnessConfig(), drift_config=self.drift_config)
        self.backend = backend
        self.service = service
        self.seed = seed
        self.server = create_server(service, as_of=self.clock.now(), clock=self.clock)
        self.clock_driver.set_backend(backend)


class AttachedSession:
    """A CLI session that can call only the public tools on a running server."""

    def __init__(self, url: str, *, call_tool: ToolCall | None = None) -> None:
        self.url = url
        self._call_tool_override = call_tool

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invoke an MCP tool over Streamable HTTP."""
        if self._call_tool_override is not None:
            return self._call_tool_override(name, arguments)
        try:
            return asyncio.run(_call_http_server(self.url, name, arguments))
        except MCPToolError:
            raise
        except (
            ConnectionError,
            OSError,
            RuntimeError,
            TimeoutError,
            ValueError,
            TypeError,
            ExceptionGroup,
        ) as exc:
            raise ConnectionError(
                f"cannot connect to MCP server at {self.url}: {_root_exception_message(exc)}"
            ) from None

    def list_tools(self) -> list[dict[str, str]]:
        """List tools through the attached server's MCP connection."""
        try:
            return asyncio.run(_list_http_tools(self.url))
        except (
            ConnectionError,
            OSError,
            RuntimeError,
            TimeoutError,
            ValueError,
            TypeError,
            ExceptionGroup,
        ) as exc:
            raise ConnectionError(
                f"cannot connect to MCP server at {self.url}: {_root_exception_message(exc)}"
            ) from None

    def advance(self, _duration: timedelta) -> datetime:
        """Attached sessions cannot control a server's simulated clock."""
        raise RuntimeError("advance is available only in embedded mode")


def create_embedded_session(
    *,
    vehicles: int,
    seed: int,
    start: datetime,
    profile_mix: dict[str, int] | None = None,
    drift_config: DriftConfig | None = None,
) -> EmbeddedSession:
    """Construct one shared simulator, clock, service, and MCP server."""
    clock = ManualClock(start)
    backend = SimulatorBackend(
        seed=seed,
        clock=clock,
        vehicles=vehicles,
        profile_mix=profile_mix,
    )
    selected_drift_config = drift_config or DriftConfig()
    service = VehicleService(backend, FreshnessConfig(), drift_config=selected_drift_config)
    return EmbeddedSession(
        backend,
        clock,
        service,
        vehicles=vehicles,
        seed=seed,
        profile_mix=profile_mix,
        drift_config=selected_drift_config,
    )


async def _call_memory_server(
    server: MCPServer, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    async with create_client_server_memory_streams() as (client_streams, server_streams):
        client_read, client_write = client_streams
        server_read, server_write = server_streams
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(
                server._lowlevel_server.run,
                server_read,
                server_write,
                server._lowlevel_server.create_initialization_options(),
            )
            async with ClientSession(client_read, client_write) as client:
                await client.initialize()
                response = await client.call_tool(name, arguments)
            tasks.cancel_scope.cancel()
    if response.is_error:
        raise MCPToolError(_error_text(response.content))
    if not isinstance(response.structured_content, dict):
        raise TypeError(f"MCP tool {name} returned no structured content")
    return response.structured_content


async def _list_memory_tools(server: MCPServer) -> list[dict[str, str]]:
    async with create_client_server_memory_streams() as (client_streams, server_streams):
        client_read, client_write = client_streams
        server_read, server_write = server_streams
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(
                server._lowlevel_server.run,
                server_read,
                server_write,
                server._lowlevel_server.create_initialization_options(),
            )
            async with ClientSession(client_read, client_write) as client:
                await client.initialize()
                result = await client.list_tools()
            tasks.cancel_scope.cancel()
    return [{"name": tool.name, "description": tool.description or ""} for tool in result.tools]


async def _call_http_server(url: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    async with (
        streamable_http_client(url) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as client,
    ):
        await client.initialize()
        response = await client.call_tool(name, arguments)
    if response.is_error:
        raise MCPToolError(_error_text(response.content))
    if not isinstance(response.structured_content, dict):
        raise TypeError(f"MCP tool {name} returned no structured content")
    return response.structured_content


async def _list_http_tools(url: str) -> list[dict[str, str]]:
    async with (
        streamable_http_client(url) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as client,
    ):
        await client.initialize()
        result = await client.list_tools()
    return [{"name": tool.name, "description": tool.description or ""} for tool in result.tools]


def _error_text(content: Sequence[object]) -> str:
    """Extract readable text from an MCP error response when it is present."""
    for item in content:
        if isinstance(item, TextContent):
            return item.text
    return "MCP server returned an error"
