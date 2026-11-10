"""Fault injection against an attached simulator MCP server."""

import time
from collections.abc import Callable
from typing import Any

from telematics.cli.session import AttachedSession, MCPToolError

ToolCall = Callable[[str, dict[str, Any]], dict[str, Any]]
Monotonic = Callable[[], float]
Sleeper = Callable[[float], None]
_FAULT_ALIASES = {
    "stale": "stale_device",
    "drift": "gps_drift",
    "blackout": "rural_blackout",
    "dupes": "duplicate_heartbeats",
    "flicker": "ignition_flicker",
    "skew": "clock_skew",
    "fuel-spike": "fuel_sensor_spike",
    "burst": "buffered_burst",
}


def _root_exception_message(error: BaseException) -> str:
    """Unwrap transport exception groups to show the actionable network cause."""
    while isinstance(error, BaseExceptionGroup) and error.exceptions:
        error = error.exceptions[0]
    return str(error)


def poll_for_verdict(
    call_tool: ToolCall,
    *,
    vehicle_id: str,
    expected: str,
    timeout_seconds: float,
    interval_seconds: float,
    monotonic: Monotonic = time.monotonic,
    sleep: Sleeper = time.sleep,
) -> int:
    """Poll the public quality report until a verdict arrives or time expires."""
    if timeout_seconds <= 0 or interval_seconds <= 0:
        raise ValueError("timeout and polling interval must be positive")
    deadline = monotonic() + timeout_seconds
    while True:
        report = call_tool("get_quality_report", {"vehicle_id": vehicle_id, "verbose": False})
        vehicles = report.get("vehicles")
        if vehicles:
            observed = vehicles[0].get("data_quality", {}).get("verdict")
        else:
            observed = report.get("data_quality", {}).get("verdict")
        if observed == expected:
            return 0
        remaining = deadline - monotonic()
        if remaining <= 0:
            return 1
        sleep(min(interval_seconds, remaining))


def inject_and_wait(
    session: AttachedSession,
    *,
    fault: str,
    vehicle_id: str,
    severity: str,
    duration: str | None,
    expected: str,
    timeout_seconds: float | None,
    interval_seconds: float = 1.0,
    monotonic: Monotonic = time.monotonic,
    sleep: Sleeper = time.sleep,
) -> int:
    """Inject one fault and optionally wait for its expected trust verdict."""
    fault = _FAULT_ALIASES.get(fault, fault)
    params: dict[str, str] = {"severity": severity}
    if duration is not None:
        params["duration"] = duration
    try:
        result = session.call_tool(
            "inject_fault",
            {"vehicle_id": vehicle_id, "fault": fault, "params": params},
        )
    except MCPToolError as exc:
        print(f"simulator rejected the request: {exc}")
        return 2
    except (OSError, RuntimeError, TimeoutError, ExceptionGroup) as exc:
        print(
            f"cannot reach simulator at {session.url}: {_root_exception_message(exc)}\n"
            "Start it with: uv run telematics serve --transport streamable-http",
        )
        return 3
    print(
        f"injected {result['fault']} on {vehicle_id} ({severity}) "
        f"[{result['fault_id']}]: {result['expected_quality_impact']}"
    )
    if timeout_seconds is None:
        return 0
    try:
        status = poll_for_verdict(
            session.call_tool,
            vehicle_id=vehicle_id,
            expected=expected,
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
            monotonic=monotonic,
            sleep=sleep,
        )
    except MCPToolError as exc:
        print(f"simulator rejected the quality request: {exc}")
        return 2
    except (OSError, RuntimeError, TimeoutError, ExceptionGroup) as exc:
        print(
            f"cannot reach simulator at {session.url}: {_root_exception_message(exc)}\n"
            "Start it with: uv run telematics serve --transport streamable-http",
        )
        return 3
    if status == 0:
        print(f"observed expected {expected} verdict for {vehicle_id}")
    else:
        print(f"timed out waiting for {expected} verdict for {vehicle_id}")
    return status
