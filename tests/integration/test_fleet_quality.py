"""Fleet-level trust must never hide a blocked vehicle behind a healthy first row."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from telematics.cli.session import EmbeddedSession, MCPToolError, create_embedded_session
from telematics.clock import ManualClock
from telematics.config import DriftConfig, FreshnessConfig
from telematics.mcp import schemas
from telematics.mcp.server import create_server
from telematics.models.telemetry import TelemetryPoint
from telematics.service.vehicles import VehicleService

_START = datetime(2025, 1, 1, tzinfo=UTC)

_FLEET_CALLS: tuple[tuple[str, dict[str, Any], type[schemas.StrictModel]], ...] = (
    ("get_quality_report", {}, schemas.QualityReportOutput),
    ("check_fleet_freshness", {}, schemas.FleetFreshnessOutput),
    ("list_quality_issues", {}, schemas.QualityIssuesOutput),
    ("check_duplicates", {"last": "1h"}, schemas.DuplicatesReportOutput),
    ("get_fuel_events", {"last": "1h"}, schemas.FuelEventsOutput),
)


def _session(vehicles: int) -> EmbeddedSession:
    return create_embedded_session(vehicles=vehicles, seed=42, start=_START)


def _block(session: EmbeddedSession, vehicle_id: str) -> None:
    session.call_tool(
        "inject_fault",
        {
            "vehicle_id": vehicle_id,
            "fault": "stale_device",
            "params": {"severity": "high"},
        },
    )


def _assert_fleet_block(payload: dict[str, Any], vehicle_id: str) -> None:
    quality = payload["data_quality"]
    assert quality["verdict"] == "BLOCK"
    assert quality["usable_for_decision"] is False
    assert quality["blocked_vehicles"] == [vehicle_id]
    assert quality["blocked_vehicle_count"] == 1


@pytest.mark.integration
def test_fleet_tools_block_when_a_non_first_vehicle_is_blocked() -> None:
    session = _session(2)
    _block(session, "LRY-0001")

    for name, arguments, model in _FLEET_CALLS:
        payload = session.call_tool(name, arguments)
        _assert_fleet_block(payload, "LRY-0001")
        model.model_validate(payload)


@pytest.mark.integration
def test_fleet_tools_block_when_the_first_vehicle_is_blocked() -> None:
    session = _session(2)
    _block(session, "TRK-0001")

    for name, arguments, model in _FLEET_CALLS:
        payload = session.call_tool(name, arguments)
        _assert_fleet_block(payload, "TRK-0001")
        model.model_validate(payload)


@pytest.mark.integration
def test_clean_fleet_stays_pass_and_usable() -> None:
    session = _session(2)

    for name, arguments, model in _FLEET_CALLS:
        payload = session.call_tool(name, arguments)
        quality = payload["data_quality"]
        assert quality["verdict"] == "PASS"
        assert quality["usable_for_decision"] is True
        assert quality["blocked_vehicles"] == []
        assert quality["blocked_vehicle_count"] == 0
        model.model_validate(payload)


@pytest.mark.integration
def test_blocked_vehicle_list_is_capped_and_counted() -> None:
    session = _session(12)
    blocked = session.backend.list_vehicle_ids()[:6]
    for vehicle_id in blocked:
        _block(session, vehicle_id)

    payload = session.call_tool("get_quality_report", {})
    quality = payload["data_quality"]

    assert quality["verdict"] == "BLOCK"
    assert quality["blocked_vehicle_count"] == 6
    assert len(quality["blocked_vehicles"]) == 5
    assert set(quality["blocked_vehicles"]) <= set(blocked)
    schemas.QualityReportOutput.model_validate(payload)


@pytest.mark.integration
def test_high_mean_does_not_override_a_blocked_vehicle() -> None:
    session = _session(12)
    _block(session, "LRY-0001")

    payload = session.call_tool("get_quality_report", {})
    quality = payload["data_quality"]

    assert quality["trust_score"] > 0.5
    assert quality["verdict"] == "BLOCK"
    assert quality["usable_for_decision"] is False


@pytest.mark.integration
def test_fleet_caveats_name_the_affected_vehicle() -> None:
    session = _session(2)
    _block(session, "LRY-0001")

    payload = session.call_tool("get_quality_report", {})
    caveats = payload["data_quality"]["caveats"]

    assert any("LRY-0001" in caveat for caveat in caveats)
    assert len(caveats) <= 11


@pytest.mark.integration
def test_inject_fault_reports_the_target_vehicle_not_the_first_vehicle() -> None:
    session = _session(2)

    payload = session.call_tool(
        "inject_fault",
        {
            "vehicle_id": "LRY-0001",
            "fault": "stale_device",
            "params": {"severity": "high"},
        },
    )

    assert payload["vehicle_id"] == "LRY-0001"
    assert payload["data_quality"]["verdict"] == "BLOCK"
    assert payload["data_quality"]["usable_for_decision"] is False
    schemas.FaultInjectionOutput.model_validate(payload)


class _EmptyBackend:
    """A fleet with no vehicles, to prove empty fleets fail structurally."""

    def list_vehicle_ids(self) -> tuple[str, ...]:
        return ()

    def get_points(self, vehicle_id: str) -> tuple[TelemetryPoint, ...]:
        raise AssertionError(f"empty backend asked for {vehicle_id}")


class _FuelBackend:
    """A static fleet where every vehicle has one unexplained fuel drop."""

    def __init__(self, vehicles: int) -> None:
        self._ids = tuple(f"FUEL-{index:04d}" for index in range(1, vehicles + 1))

    def list_vehicle_ids(self) -> tuple[str, ...]:
        return self._ids

    def get_points(self, vehicle_id: str) -> tuple[TelemetryPoint, ...]:
        del vehicle_id
        return (
            _fuel_point(_START - timedelta(minutes=2), 80.0, serial_number=1),
            _fuel_point(_START - timedelta(minutes=1), 60.0, serial_number=2),
        )


def _fuel_point(when: datetime, fuel: float, *, serial_number: int) -> TelemetryPoint:
    return TelemetryPoint(
        device_time=when,
        latitude=-1.2921,
        longitude=36.8219,
        speed_kph=0.0,
        course_deg=0,
        satellites=9,
        serial_number=serial_number,
        received_at=when,
        ignition_on=True,
        fuel_level_percent=fuel,
    )


def _static_session(backend: object, *, vehicles: int) -> EmbeddedSession:
    clock = ManualClock(_START)
    service = VehicleService(backend, FreshnessConfig())  # type: ignore[arg-type]
    return EmbeddedSession(
        backend,  # type: ignore[arg-type]
        clock,
        service,
        vehicles=vehicles,
        seed=42,
        profile_mix=None,
        drift_config=DriftConfig(),
    )


class _TickClock:
    """Counts clock reads so a handler that reads twice is visible."""

    def __init__(self) -> None:
        self.calls = 0

    def now(self) -> datetime:
        self.calls += 1
        return _START + timedelta(seconds=self.calls)


def _assert_invalid_request(session: EmbeddedSession, name: str, arguments: dict[str, Any]) -> None:
    with pytest.raises(MCPToolError, match="INVALID_REQUEST"):
        session.call_tool(name, arguments)


def _assert_limit_bounds(session: EmbeddedSession, name: str) -> None:
    with pytest.raises(MCPToolError, match="greater than or equal to 1"):
        session.call_tool(name, {"limit": 0})
    with pytest.raises(MCPToolError, match="less than or equal to 200"):
        session.call_tool(name, {"limit": 201})


@pytest.mark.integration
def test_empty_fleet_returns_a_structured_invalid_request() -> None:
    session = _static_session(_EmptyBackend(), vehicles=0)

    for name, arguments, _model in _FLEET_CALLS:
        _assert_invalid_request(session, name, arguments)


@pytest.mark.integration
def test_empty_fleet_still_lists_no_vehicles() -> None:
    session = _static_session(_EmptyBackend(), vehicles=0)

    payload = session.call_tool("list_vehicles", {})

    assert payload["vehicles"] == []
    assert payload["next_cursor"] is None


@pytest.mark.integration
def test_freshness_pagination_is_disjoint_and_complete() -> None:
    session = _session(12)
    all_ids = list(session.backend.list_vehicle_ids())

    pages: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        arguments: dict[str, Any] = {"limit": 5}
        if cursor is not None:
            arguments["cursor"] = cursor
        page = session.call_tool("check_fleet_freshness", arguments)
        pages.append(page)
        cursor = page["next_cursor"]
        if cursor is None:
            break

    returned = [vehicle["vehicle_id"] for page in pages for vehicle in page["vehicles"]]
    assert returned == all_ids
    assert [len(page["vehicles"]) for page in pages] == [5, 5, 2]
    assert all(page["vehicle_count"] == 12 for page in pages)
    for page in pages:
        schemas.FleetFreshnessOutput.model_validate(page)


@pytest.mark.integration
def test_freshness_rejects_an_unknown_cursor_and_enforces_limit_bounds() -> None:
    session = _session(3)

    with pytest.raises(MCPToolError, match="invalid vehicle cursor"):
        session.call_tool("check_fleet_freshness", {"cursor": "NOPE-9999"})
    assert len(session.call_tool("check_fleet_freshness", {"limit": 1})["vehicles"]) == 1
    _assert_limit_bounds(session, "check_fleet_freshness")


@pytest.mark.integration
def test_fleet_report_returns_the_ten_worst_with_totals() -> None:
    session = _session(12)
    blocked = session.backend.list_vehicle_ids()[:6]
    for vehicle_id in blocked:
        _block(session, vehicle_id)

    payload = session.call_tool("get_quality_report", {})

    assert len(payload["vehicles"]) == 10
    assert payload["vehicle_count"] == 12
    counts = payload["verdict_counts"]
    assert sum(counts.values()) == 12
    assert counts["BLOCK"] == 6
    assert sum(payload["trust_score_histogram"].values()) == 12
    assert {vehicle["vehicle_id"] for vehicle in payload["vehicles"][:6]} == set(blocked)
    schemas.QualityReportOutput.model_validate(payload)


@pytest.mark.integration
def test_clean_fleet_report_has_complete_counts_and_histogram() -> None:
    session = _session(12)

    payload = session.call_tool("get_quality_report", {})

    counts = payload["verdict_counts"]
    assert counts == {"PASS": 12, "WARN": 0, "BLOCK": 0}
    assert payload["trust_score_histogram"] == {
        "0.0-0.2": 0,
        "0.2-0.4": 0,
        "0.4-0.6": 0,
        "0.6-0.8": 0,
        "0.8-1.0": 12,
    }
    assert payload["vehicle_count"] == 12


@pytest.mark.integration
def test_quality_issues_truncates_and_counts() -> None:
    session = _session(4)
    for vehicle_id in session.backend.list_vehicle_ids()[:3]:
        _block(session, vehicle_id)

    page = session.call_tool("list_quality_issues", {"limit": 1})
    assert len(page["issues"]) == 1
    assert page["total_issues"] >= 3
    assert page["truncated"] is True
    schemas.QualityIssuesOutput.model_validate(page)

    full = session.call_tool("list_quality_issues", {"limit": 200})
    assert full["truncated"] is False
    assert len(full["issues"]) == full["total_issues"]


@pytest.mark.integration
def test_quality_issues_enforces_limit_bounds() -> None:
    session = _session(2)

    assert len(session.call_tool("list_quality_issues", {"limit": 1})["issues"]) <= 1
    _assert_limit_bounds(session, "list_quality_issues")


@pytest.mark.integration
def test_fuel_events_truncates_and_counts() -> None:
    session = _static_session(_FuelBackend(3), vehicles=3)

    page = session.call_tool("get_fuel_events", {"limit": 2})
    assert len(page["events"]) == 2
    assert page["total_events"] == 3
    assert page["truncated"] is True
    schemas.FuelEventsOutput.model_validate(page)

    full = session.call_tool("get_fuel_events", {"limit": 200})
    assert len(full["events"]) == 3
    assert full["total_events"] == 3
    assert full["truncated"] is False


@pytest.mark.integration
def test_fuel_events_enforces_limit_bounds() -> None:
    session = _static_session(_FuelBackend(1), vehicles=1)

    assert len(session.call_tool("get_fuel_events", {"limit": 1})["events"]) == 1
    _assert_limit_bounds(session, "get_fuel_events")


@pytest.mark.integration
@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        pytest.param("list_vehicles", {}, id="list_vehicles"),
        pytest.param("get_vehicle_location", {"vehicle_id": "TRK-0001"}, id="get_vehicle_location"),
        pytest.param(
            "get_trip_history", {"vehicle_id": "TRK-0001", "last": "1h"}, id="get_trip_history"
        ),
        pytest.param("get_fuel_events", {"last": "1h"}, id="get_fuel_events"),
        pytest.param("get_quality_report", {}, id="get_quality_report"),
        pytest.param("check_fleet_freshness", {}, id="check_fleet_freshness"),
        pytest.param(
            "check_gps_drift", {"vehicle_id": "TRK-0001", "last": "1h"}, id="check_gps_drift"
        ),
        pytest.param("check_duplicates", {"last": "1h"}, id="check_duplicates"),
        pytest.param("list_quality_issues", {}, id="list_quality_issues"),
        pytest.param(
            "inject_fault",
            {"vehicle_id": "TRK-0001", "fault": "stale_device", "params": {}},
            id="inject_fault",
        ),
        pytest.param("reset_simulator", {}, id="reset_simulator"),
    ],
)
def test_each_tool_reads_the_clock_once(name: str, arguments: dict[str, Any]) -> None:
    session = _session(2)
    clock = _TickClock()
    session.server = create_server(session.service, as_of=_START, clock=clock)

    session.call_tool(name, arguments)

    assert clock.calls == 1
