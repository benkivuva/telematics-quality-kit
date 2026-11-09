"""Embedded and attached CLI session contract tests."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from telematics.cli.session import AttachedSession, create_embedded_session
from telematics.mcp.schemas import ListVehiclesOutput

_START = datetime(2025, 1, 1, tzinfo=UTC)


@pytest.mark.integration
def test_embedded_session_calls_the_public_mcp_tool_surface() -> None:
    session = create_embedded_session(vehicles=1, seed=42, start=_START)
    result = session.call_tool("list_vehicles", {"limit": 1})

    payload = ListVehiclesOutput.model_validate(result)
    assert len(payload.vehicles) == 1
    assert payload.vehicles[0].vehicle_id == "TRK-0001"


@pytest.mark.integration
def test_embedded_mcp_quality_reads_the_current_injected_clock() -> None:
    session = create_embedded_session(vehicles=1, seed=42, start=_START)
    before = session.call_tool("get_vehicle_location", {"vehicle_id": "TRK-0001"})

    session.clock.advance(timedelta(seconds=61))
    after = session.call_tool("get_vehicle_location", {"vehicle_id": "TRK-0001"})

    assert before["age_seconds"] == 0
    assert after["age_seconds"] == 61
    assert after["data_quality"]["verdict"] == "WARN"


@pytest.mark.unit
def test_attached_session_uses_only_its_mcp_transport() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        calls.append((name, arguments))
        return {"schema_version": "1.0", "vehicles": [], "next_cursor": None}

    session = AttachedSession("http://127.0.0.1:8000/mcp", call_tool=call_tool)

    assert session.call_tool("list_vehicles", {"limit": 3})["vehicles"] == []
    assert calls == [("list_vehicles", {"limit": 3})]

    with pytest.raises(RuntimeError, match="embedded mode"):
        session.advance(timedelta(minutes=1))
