"""In-process contract coverage for the v0.1 MCP surface."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import cast

import anyio
import pytest
from mcp.client.session import ClientSession
from mcp.shared.memory import create_client_server_memory_streams
from pydantic import ValidationError

from telematics.backends.base import FleetBackend
from telematics.backends.simulator import SimulatorBackend
from telematics.clock import ManualClock
from telematics.config import FreshnessConfig
from telematics.mcp import schemas
from telematics.mcp.server import create_server
from telematics.models.telemetry import TelemetryPoint
from telematics.service.vehicles import VehicleService

_NOW = datetime(2025, 1, 1, tzinfo=UTC)
_TOOL_MODELS: dict[str, type[schemas.StrictModel]] = {
    "list_vehicles": schemas.ListVehiclesOutput,
    "get_vehicle_location": schemas.VehicleLocationOutput,
    "get_trip_history": schemas.TripHistoryOutput,
    "get_fuel_events": schemas.FuelEventsOutput,
    "get_quality_report": schemas.QualityReportOutput,
    "check_fleet_freshness": schemas.FleetFreshnessOutput,
    "check_gps_drift": schemas.DriftReportOutput,
    "check_duplicates": schemas.DuplicatesReportOutput,
    "list_quality_issues": schemas.QualityIssuesOutput,
    "inject_fault": schemas.FaultInjectionOutput,
    "reset_simulator": schemas.ResetSimulatorOutput,
}


class ReadOnlyBackend:
    def list_vehicle_ids(self) -> tuple[str, ...]:
        return ("TRK-0001",)

    def get_points(self, vehicle_id: str) -> tuple[TelemetryPoint, ...]:
        return (
            TelemetryPoint(
                _NOW - timedelta(minutes=10),
                -1.28,
                36.82,
                0.0,
                0,
                8,
                1,
                received_at=_NOW,
            ),
        )


@pytest.mark.integration
def test_all_eleven_tools_validate_models_annotations_and_resources() -> None:
    asyncio.run(_assert_full_surface())


async def _assert_full_surface() -> None:
    service = VehicleService(
        SimulatorBackend(seed=8, clock=ManualClock(_NOW), vehicles=2), FreshnessConfig()
    )
    server = create_server(service, as_of=_NOW)
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
                listed = await client.list_tools()
                tool_specs = {tool.name: tool for tool in listed.tools}
                assert set(tool_specs) == set(_TOOL_MODELS)
                for name, model in _TOOL_MODELS.items():
                    assert model.model_config["extra"] == "forbid"
                    spec = tool_specs[name]
                    assert spec.input_schema.get("additionalProperties") is False
                    assert spec.output_schema is not None
                    if name in {"inject_fault", "reset_simulator"}:
                        assert spec.annotations is not None
                        assert spec.annotations.destructive_hint is True
                        assert spec.annotations.idempotent_hint is False
                    else:
                        assert spec.annotations is not None
                        assert spec.annotations.read_only_hint is True
                        assert spec.annotations.idempotent_hint is True

                calls: dict[str, dict[str, object]] = {
                    "list_vehicles": {"limit": 10},
                    "get_vehicle_location": {"vehicle_id": "TRK-0001"},
                    "get_trip_history": {"vehicle_id": "TRK-0001", "last": "1h"},
                    "get_fuel_events": {"last": "1h"},
                    "get_quality_report": {},
                    "check_fleet_freshness": {},
                    "check_gps_drift": {"vehicle_id": "TRK-0001", "last": "1h"},
                    "check_duplicates": {"last": "1h"},
                    "list_quality_issues": {},
                    "inject_fault": {
                        "vehicle_id": "TRK-0001",
                        "fault": "stale_device",
                        "params": {},
                    },
                    "reset_simulator": {},
                }
                for name, arguments in calls.items():
                    response = await client.call_tool(name, arguments)
                    assert not response.is_error
                    payload = _structured(response.structured_content)
                    parsed = _TOOL_MODELS[name].model_validate(payload)
                    assert parsed.schema_version == "1.0"
                    if name == "inject_fault":
                        post_fault = await client.call_tool("list_vehicles", {"limit": 1})
                        assert not post_fault.is_error
                        vehicles = schemas.ListVehiclesOutput.model_validate(
                            _structured(post_fault.structured_content)
                        )
                        assert vehicles.vehicles[0].data_quality.verdict == "BLOCK"
                invalid_input = await client.call_tool(
                    "get_vehicle_location",
                    {"vehicle_id": "TRK-0001", "unexpected": True},
                )
                assert invalid_input.is_error

                resource_list = await client.list_resources()
                uris = {str(resource.uri) for resource in resource_list.resources}
                assert {"quality://checks", "fleet://profiles"} <= uris
                quality_resource = await client.read_resource("quality://checks")
                assert "freshness" in str(quality_resource.contents[0].text)
                profile_resource = await client.read_resource("fleet://profiles")
                assert "teltonika" in str(profile_resource.contents[0].text)
                prompt_list = await client.list_prompts()
                prompts = {prompt.name for prompt in prompt_list.prompts}
                assert {
                    "fleet_health_briefing",
                    "investigate_vehicle",
                    "fault_drill",
                } <= prompts
                briefing = await client.get_prompt("fleet_health_briefing")
                assert "get_quality_report" in briefing.messages[0].content.text
                investigation = await client.get_prompt(
                    "investigate_vehicle", {"vehicle_id": "TRK-0001"}
                )
                assert "TRK-0001" in investigation.messages[0].content.text
                drill = await client.get_prompt("fault_drill", {"vehicle_id": "TRK-0001"})
                assert "reset_simulator" in drill.messages[0].content.text
            tasks.cancel_scope.cancel()


@pytest.mark.integration
def test_tool_errors_include_machine_readable_code() -> None:
    asyncio.run(_assert_structured_tool_error())


async def _assert_structured_tool_error() -> None:
    service = VehicleService(
        SimulatorBackend(seed=8, clock=ManualClock(_NOW), vehicles=1), FreshnessConfig()
    )
    server = create_server(service, as_of=_NOW)
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
                response = await client.call_tool("get_vehicle_location", {"vehicle_id": "MISSING"})
                assert response.is_error
                error_text = response.content[0].text
                error = json.loads(error_text[error_text.find("{") :])
                assert error["code"] == "INVALID_REQUEST"
            tasks.cancel_scope.cancel()


@pytest.mark.integration
def test_fault_tools_are_hidden_without_faults_capability() -> None:
    asyncio.run(_assert_fault_tools_hidden())


async def _assert_fault_tools_hidden() -> None:
    service = VehicleService(cast(FleetBackend, ReadOnlyBackend()), FreshnessConfig())
    server = create_server(service, as_of=_NOW)
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
                names = {tool.name for tool in (await client.list_tools()).tools}
                assert "inject_fault" not in names
                assert "reset_simulator" not in names
            tasks.cancel_scope.cancel()


@pytest.mark.integration
def test_block_is_successful_response_with_withheld_values() -> None:
    asyncio.run(_assert_block_is_normal_result())


async def _assert_block_is_normal_result() -> None:
    service = VehicleService(cast(FleetBackend, ReadOnlyBackend()), FreshnessConfig())
    server = create_server(service, as_of=_NOW)
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
                response = await client.call_tool(
                    "get_trip_history", {"vehicle_id": "TRK-0001", "last": "1h"}
                )
                assert not response.is_error
                payload = schemas.TripHistoryOutput.model_validate(
                    _structured(response.structured_content)
                )
                assert payload.data_quality.verdict == "BLOCK"
                assert payload.data_quality.usable_for_decision is False
                assert payload.trips
                assert "distance_km" in payload.trips[0].withheld
            tasks.cancel_scope.cancel()


@pytest.mark.integration
def test_all_input_models_reject_unknown_fields() -> None:
    for model in schemas.INPUT_MODELS:
        with pytest.raises(ValidationError):
            model.model_validate({"unexpected": "value"})


def _structured(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value
