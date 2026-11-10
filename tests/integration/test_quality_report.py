"""`get_quality_report` returns one vehicle directly or the fleet summary."""

from datetime import UTC, datetime, timedelta

import pytest

from telematics.cli.session import create_embedded_session
from telematics.mcp.schemas import QualityReportOutput

_START = datetime(2025, 1, 1, tzinfo=UTC)


@pytest.mark.integration
def test_single_vehicle_report_is_returned_directly() -> None:
    session = create_embedded_session(vehicles=1, seed=42, start=_START)

    report = session.call_tool("get_quality_report", {"vehicle_id": "TRK-0001"})

    assert "vehicles" not in report
    assert report["vehicle_id"] == "TRK-0001"
    assert report["data_quality"]["verdict"] == "PASS"
    QualityReportOutput.model_validate(report)


@pytest.mark.integration
def test_fleet_report_keeps_the_vehicles_list() -> None:
    session = create_embedded_session(vehicles=2, seed=42, start=_START)

    report = session.call_tool("get_quality_report", {})

    assert "vehicle_id" not in report
    assert [vehicle["vehicle_id"] for vehicle in report["vehicles"]] == ["TRK-0001", "LRY-0001"]
    QualityReportOutput.model_validate(report)


@pytest.mark.integration
def test_reset_simulator_can_clear_only_a_selected_fault_and_vehicle() -> None:
    session = create_embedded_session(vehicles=2, seed=42, start=_START)
    first_id, _ = session.backend.inject_fault("TRK-0001", "gps_drift", {"severity": "high"})
    second_id, _ = session.backend.inject_fault("LRY-0001", "stale_device", {"severity": "high"})

    result = session.call_tool("reset_simulator", {"fault": "gps_drift", "vehicle_id": "TRK-0001"})

    assert result["cleared_faults"] == 1
    assert first_id not in session.backend._active_faults
    assert second_id in session.backend._active_faults
    QualityReportOutput.model_validate(
        session.call_tool("get_quality_report", {"vehicle_id": "TRK-0001"})
    )


@pytest.mark.integration
def test_high_gps_drift_impact_is_an_asserted_drift_block() -> None:
    session = create_embedded_session(vehicles=1, seed=42, start=_START)

    injected = session.call_tool(
        "inject_fault",
        {"vehicle_id": "TRK-0001", "fault": "gps_drift", "params": {"severity": "high"}},
    )
    session.advance(timedelta(minutes=2))
    report = session.call_tool("get_quality_report", {"vehicle_id": "TRK-0001", "verbose": True})
    drift = next(check for check in report["data_quality"]["checks"] if check["name"] == "drift")

    assert injected["expected_quality_impact"] == (
        "drift BLOCK within 2m at high severity (implausible consecutive fixes)"
    )
    assert drift["verdict"] == "BLOCK"
