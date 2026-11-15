"""MCP v2 registration for the v0.1 query, quality, and simulator surface."""

import json
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from functools import wraps
from itertools import pairwise
from typing import Literal, cast

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from telematics.clock import Clock
from telematics.mcp import schemas
from telematics.mcp.prompts import register_prompts
from telematics.mcp.resources import register_resources
from telematics.models.quality import CheckResult, Verdict, worst_verdict
from telematics.models.telemetry import TelemetryPoint
from telematics.service.vehicles import DataQuality, VehicleService, VehicleSummary

_READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)
_DESTRUCTIVE = ToolAnnotations(destructive_hint=True, idempotent_hint=False, open_world_hint=False)
_NEXT_CHECK = {
    "freshness": "check_fleet_freshness",
    "drift": "check_gps_drift",
    "duplicates": "check_duplicates",
    "ignition": "get_quality_report",
    "plausibility": "get_quality_report",
    "fuel": "get_fuel_events",
}
_FLEET_REPORT_LIMIT = 10
_HISTOGRAM_LABELS = ("0.0-0.2", "0.2-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0")


def _structured_errors[**P, R](function: Callable[P, R]) -> Callable[P, R]:
    """Return service validation failures as machine-readable MCP tool errors."""

    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return function(*args, **kwargs)
        except (ValueError, KeyError) as exc:
            raise ToolError(
                json.dumps(
                    {"code": "INVALID_REQUEST", "message": str(exc)},
                    sort_keys=True,
                )
            ) from exc

    return wrapped


def _bounds(
    *, as_of: datetime, last: str | None, start: datetime | None, end: datetime | None
) -> tuple[datetime, datetime]:
    if start is not None and end is not None:
        return start, end
    duration = last or "24h"
    amount, unit = int(duration[:-1]), duration[-1]
    delta = timedelta(seconds=amount * {"m": 60, "h": 3600, "d": 86400}[unit])
    return as_of - delta, as_of


def _check_outputs(checks: tuple[CheckResult, ...]) -> list[schemas.CheckOutput]:
    return [
        schemas.CheckOutput(
            name=check.name,
            verdict=check.verdict.value,
            score=check.score,
            metric=dict(check.metric),
        )
        for check in checks
    ]


def _quality_output(
    quality: DataQuality,
    *,
    as_of: datetime,
    start: datetime,
    end: datetime,
    verbose: bool = False,
) -> schemas.DataQualityOutput:
    return schemas.DataQualityOutput(
        verdict=quality.verdict.value,
        label=cast(Literal["trust it", "be careful", "don't trust it"], quality.label),
        symbol=cast(Literal["✓", "⚠", "⛔"], quality.symbol),
        trust_score=quality.trust_score,
        usable_for_decision=quality.usable_for_decision,
        caveats=list(quality.caveats),
        withheld=list(quality.withheld),
        blocked_vehicles=list(quality.blocked_vehicles),
        blocked_vehicle_count=quality.blocked_vehicle_count,
        checks=_check_outputs(quality.checks) if verbose else [],
        as_of=as_of,
        window=schemas.WindowOutput(start=start, end=end),
    )


def _vehicle_output(
    summary: VehicleSummary,
    *,
    as_of: datetime,
    verbose: bool = False,
) -> schemas.VehicleOutput:
    return schemas.VehicleOutput(
        vehicle_id=summary.vehicle_id,
        device_time=summary.latest.device_time,
        latitude=summary.latest.latitude,
        longitude=summary.latest.longitude,
        speed_kph=summary.latest.speed_kph,
        data_quality=_quality_output(
            summary.data_quality,
            as_of=as_of,
            start=summary.points[0].device_time,
            end=summary.latest.device_time,
            verbose=verbose,
        ),
    )


def _evaluate(
    service: VehicleService,
    vehicle_id: str,
    *,
    as_of: datetime,
    start: datetime | None = None,
    end: datetime | None = None,
) -> VehicleSummary:
    return service.evaluate_vehicle(vehicle_id, as_of=as_of, start=start, end=end)


def _cursor_start(ids: Sequence[str], cursor: str | None) -> int:
    """Return the page offset for a last-seen vehicle ID cursor."""
    if cursor is None:
        return 0
    try:
        return ids.index(cursor) + 1
    except ValueError as exc:
        raise ValueError("invalid vehicle cursor") from exc


def _fleet_rank(summary: VehicleSummary) -> tuple[int, float]:
    """Order the fleet worst first by severity and trust score, stable on ties."""
    quality = summary.data_quality
    return (-quality.verdict.severity, quality.trust_score)


def _verdict_counts(vehicles: Sequence[VehicleSummary]) -> dict[str, int]:
    counts = {"PASS": 0, "WARN": 0, "BLOCK": 0}
    for item in vehicles:
        counts[item.data_quality.verdict.value] += 1
    return counts


def _trust_score_histogram(vehicles: Sequence[VehicleSummary]) -> dict[str, int]:
    counts = dict.fromkeys(_HISTOGRAM_LABELS, 0)
    for item in vehicles:
        index = min(int(item.data_quality.trust_score * 5), len(_HISTOGRAM_LABELS) - 1)
        counts[_HISTOGRAM_LABELS[index]] += 1
    return counts


def create_server(
    service: VehicleService, *, as_of: datetime, clock: Clock | None = None
) -> MCPServer:
    """Build an MCP server with the contract's 11 v0.1 tools."""
    server = MCPServer(name="telematics-quality-kit", version="0.1.0")

    def current_time() -> datetime:
        return clock.now() if clock is not None else as_of

    @server.tool(
        name="list_vehicles",
        description="List synthetic vehicles. Relay each data_quality label and caveat.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    @_structured_errors
    def list_vehicles(limit: int = 50, cursor: str | None = None) -> schemas.ListVehiclesOutput:
        request = schemas.ListVehiclesInput.model_validate({"limit": limit, "cursor": cursor})
        now = current_time()
        summaries = service.list_vehicles(as_of=now, limit=request.limit, cursor=request.cursor)
        ids = service.list_vehicle_ids()
        last_id = summaries[-1].vehicle_id if summaries else None
        next_cursor = last_id if last_id is not None and ids.index(last_id) < len(ids) - 1 else None
        return schemas.ListVehiclesOutput(
            vehicles=[_vehicle_output(item, as_of=now) for item in summaries],
            next_cursor=next_cursor,
        )

    @server.tool(
        name="get_vehicle_location",
        description="Return the latest location and age. BLOCK means do not use the value for decisions.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    @_structured_errors
    def get_vehicle_location(vehicle_id: str) -> schemas.VehicleLocationOutput:
        request = schemas.VehicleIdInput.model_validate({"vehicle_id": vehicle_id})
        now = current_time()
        item = _evaluate(service, request.vehicle_id, as_of=now)
        return schemas.VehicleLocationOutput(
            vehicle_id=item.vehicle_id,
            device_time=item.latest.device_time,
            latitude=item.latest.latitude,
            longitude=item.latest.longitude,
            speed_kph=item.latest.speed_kph,
            age_seconds=item.data_quality.age_seconds,
            data_quality=_quality_output(
                item.data_quality,
                as_of=now,
                start=item.points[0].device_time,
                end=item.latest.device_time,
            ),
        )

    @server.tool(
        name="get_trip_history",
        description="Return trip history; affected distance is withheld on BLOCK.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    @_structured_errors
    def get_trip_history(
        vehicle_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
        last: str | None = None,
    ) -> schemas.TripHistoryOutput:
        request = schemas.TripHistoryInput.model_validate(
            {"vehicle_id": vehicle_id, "start": start, "end": end, "last": last}
        )
        now = current_time()
        window_start, window_end = _bounds(
            as_of=now, last=request.last, start=request.start, end=request.end
        )
        item = _evaluate(
            service,
            request.vehicle_id,
            as_of=now,
            start=window_start,
            end=window_end,
        )
        withheld = "trip_distance" in item.data_quality.withheld
        return schemas.TripHistoryOutput(
            vehicle_id=request.vehicle_id,
            trips=[
                schemas.TripOutput(
                    start=item.points[0].device_time,
                    end=item.latest.device_time,
                    distance_km=None if withheld else _trip_distance(item.points),
                    withheld=["distance_km"] if withheld else [],
                )
            ],
            data_quality=_quality_output(
                item.data_quality,
                as_of=now,
                start=window_start,
                end=window_end,
            ),
        )

    @server.tool(
        name="get_fuel_events",
        description="List unexplained fuel sensor drops in a time window.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    @_structured_errors
    def get_fuel_events(
        vehicle_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        last: str | None = None,
        limit: int = 50,
    ) -> schemas.FuelEventsOutput:
        request = schemas.FuelEventsInput.model_validate(
            {"vehicle_id": vehicle_id, "start": start, "end": end, "last": last, "limit": limit}
        )
        now = current_time()
        window_start, window_end = _bounds(
            as_of=now, last=request.last, start=request.start, end=request.end
        )
        summaries: tuple[VehicleSummary, ...]
        if request.vehicle_id is not None:
            item = _evaluate(
                service,
                request.vehicle_id,
                as_of=now,
                start=window_start,
                end=window_end,
            )
            summaries = (item,)
            quality = item.data_quality
        else:
            fleet = service.evaluate_fleet(as_of=now, start=window_start, end=window_end)
            summaries = fleet.vehicles
            quality = fleet.data_quality
        events: list[schemas.FuelEventOutput] = []
        for item in summaries:
            fuel_check = next(check for check in item.data_quality.checks if check.name == "fuel")
            if fuel_check.verdict is not Verdict.PASS:
                events.append(
                    schemas.FuelEventOutput(
                        vehicle_id=item.vehicle_id,
                        device_time=item.latest.device_time,
                        drop_percent=float(fuel_check.metric.get("unexplained_drop", 0)),
                        quality_flag="unexplained_drop",
                    )
                )
        return schemas.FuelEventsOutput(
            events=events[: request.limit],
            total_events=len(events),
            truncated=len(events) > request.limit,
            data_quality=_quality_output(
                quality,
                as_of=now,
                start=window_start,
                end=window_end,
            ),
        )

    @server.tool(
        name="get_quality_report",
        description=(
            "Explain quality checks and scores; pass vehicle_id for that vehicle's report, "
            "or omit it for the fleet summary. Use verbose for per-check details."
        ),
        annotations=_READ_ONLY,
        structured_output=True,
    )
    @_structured_errors
    def get_quality_report(
        vehicle_id: str | None = None, verbose: bool = False
    ) -> schemas.QualityReportOutput:
        request = schemas.QualityReportInput.model_validate(
            {"vehicle_id": vehicle_id, "verbose": verbose}
        )
        now = current_time()
        if request.vehicle_id is not None:
            item = _evaluate(service, request.vehicle_id, as_of=now)
            vehicle = _vehicle_output(item, as_of=now, verbose=request.verbose)
            return schemas.QualityReportOutput(
                vehicle_id=vehicle.vehicle_id,
                device_time=vehicle.device_time,
                latitude=vehicle.latitude,
                longitude=vehicle.longitude,
                speed_kph=vehicle.speed_kph,
                data_quality=vehicle.data_quality,
            )
        fleet = service.evaluate_fleet(as_of=now)
        ranked = sorted(fleet.vehicles, key=_fleet_rank)
        return schemas.QualityReportOutput(
            vehicle_id=None,
            fleet_trust_score=fleet.data_quality.trust_score,
            vehicle_count=len(fleet.vehicles),
            verdict_counts=_verdict_counts(fleet.vehicles),
            trust_score_histogram=_trust_score_histogram(fleet.vehicles),
            vehicles=[
                _vehicle_output(item, as_of=now, verbose=request.verbose)
                for item in ranked[:_FLEET_REPORT_LIMIT]
            ],
            data_quality=_quality_output(
                fleet.data_quality,
                as_of=now,
                start=min(item.points[0].device_time for item in fleet.vehicles),
                end=max(item.latest.device_time for item in fleet.vehicles),
            ),
        )

    @server.tool(
        name="check_fleet_freshness",
        description="Check each vehicle's reporting age and the fleet trust score.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    @_structured_errors
    def check_fleet_freshness(
        limit: int = 50, cursor: str | None = None
    ) -> schemas.FleetFreshnessOutput:
        request = schemas.FleetFreshnessInput.model_validate({"limit": limit, "cursor": cursor})
        now = current_time()
        fleet = service.evaluate_fleet(as_of=now)
        ids = [item.vehicle_id for item in fleet.vehicles]
        start = _cursor_start(ids, request.cursor)
        page = fleet.vehicles[start : start + request.limit]
        next_cursor = page[-1].vehicle_id if page and start + request.limit < len(ids) else None
        return schemas.FleetFreshnessOutput(
            fleet_trust_score=fleet.data_quality.trust_score,
            vehicles=[
                schemas.FleetFreshnessVehicleOutput(
                    vehicle_id=item.vehicle_id,
                    age_seconds=item.data_quality.age_seconds,
                    verdict=next(
                        check for check in item.data_quality.checks if check.name == "freshness"
                    ).verdict.value,
                )
                for item in page
            ],
            vehicle_count=len(ids),
            next_cursor=next_cursor,
            data_quality=_quality_output(
                fleet.data_quality,
                as_of=now,
                start=min(item.points[0].device_time for item in fleet.vehicles),
                end=max(item.latest.device_time for item in fleet.vehicles),
            ),
        )

    @server.tool(
        name="check_gps_drift",
        description="Check one vehicle for GPS jumps and stationary jitter.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    @_structured_errors
    def check_gps_drift(
        vehicle_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
        last: str | None = None,
    ) -> schemas.DriftReportOutput:
        request = schemas.DriftReportInput.model_validate(
            {"vehicle_id": vehicle_id, "start": start, "end": end, "last": last}
        )
        now = current_time()
        window_start, window_end = _bounds(
            as_of=now, last=request.last, start=request.start, end=request.end
        )
        item = _evaluate(
            service,
            request.vehicle_id,
            as_of=now,
            start=window_start,
            end=window_end,
        )
        check = next(check for check in item.data_quality.checks if check.name == "drift")
        return schemas.DriftReportOutput(
            vehicle_id=request.vehicle_id,
            verdict=check.verdict.value,
            flagged_points=int(check.metric["flagged_points"]),
            total_points=int(check.metric["total_points"]),
            flagged_fraction=float(check.metric["flagged_fraction"]),
            data_quality=_quality_output(
                item.data_quality,
                as_of=now,
                start=window_start,
                end=window_end,
            ),
        )

    @server.tool(
        name="check_duplicates",
        description="Check the selected window for repeated records and heartbeat storms.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    @_structured_errors
    def check_duplicates(
        start: datetime | None = None,
        end: datetime | None = None,
        last: str | None = None,
    ) -> schemas.DuplicatesReportOutput:
        request = schemas.DuplicatesReportInput.model_validate(
            {"start": start, "end": end, "last": last}
        )
        now = current_time()
        window_start, window_end = _bounds(
            as_of=now, last=request.last, start=request.start, end=request.end
        )
        fleet = service.evaluate_fleet(as_of=now, start=window_start, end=window_end)
        checks: list[CheckResult] = [
            next(check for check in item.data_quality.checks if check.name == "duplicates")
            for item in fleet.vehicles
        ]
        return schemas.DuplicatesReportOutput(
            duplicate_count=sum(int(check.metric["duplicate_count"]) for check in checks),
            duplicate_fraction=(
                sum(float(check.metric["duplicate_fraction"]) for check in checks) / len(checks)
                if checks
                else 0.0
            ),
            heartbeat_rate_ratio=max(
                (float(check.metric["heartbeat_rate_ratio"]) for check in checks), default=0.0
            ),
            verdict=worst_verdict(check.verdict for check in checks).value,
            data_quality=_quality_output(
                fleet.data_quality,
                as_of=now,
                start=window_start,
                end=window_end,
            ),
        )

    @server.tool(
        name="list_quality_issues",
        description="List WARN and BLOCK quality findings with a suggested follow-up tool.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    @_structured_errors
    def list_quality_issues(
        min_verdict: str = "WARN", limit: int = 50
    ) -> schemas.QualityIssuesOutput:
        request = schemas.QualityIssuesInput.model_validate(
            {"min_verdict": min_verdict, "limit": limit}
        )
        min_level = Verdict(request.min_verdict).severity
        now = current_time()
        fleet = service.evaluate_fleet(as_of=now)
        issues: list[schemas.QualityIssueOutput] = []
        for item in fleet.vehicles:
            for check in item.data_quality.checks:
                if check.verdict.severity >= min_level:
                    issues.append(
                        schemas.QualityIssueOutput(
                            vehicle_id=item.vehicle_id,
                            check=check.name,
                            verdict=cast(Literal["WARN", "BLOCK"], check.verdict.value),
                            score=check.score,
                            suggested_next_check=_NEXT_CHECK[check.name],
                        )
                    )
        issues.sort(
            key=lambda issue: (
                0 if issue.verdict == "BLOCK" else 1,
                issue.score,
                issue.vehicle_id,
                issue.check,
            )
        )
        return schemas.QualityIssuesOutput(
            issues=issues[: request.limit],
            total_issues=len(issues),
            truncated=len(issues) > request.limit,
            data_quality=_quality_output(
                fleet.data_quality,
                as_of=now,
                start=min(item.points[0].device_time for item in fleet.vehicles),
                end=max(item.latest.device_time for item in fleet.vehicles),
            ),
        )

    fault_capability = service.fault_capability()
    if fault_capability is not None:

        @server.tool(
            name="inject_fault",
            description="Inject a named reversible fault into the synthetic simulator only.",
            annotations=_DESTRUCTIVE,
            structured_output=True,
        )
        @_structured_errors
        def inject_fault(
            vehicle_id: str,
            fault: schemas.FaultName,
            params: dict[str, int | float | str] | None = None,
        ) -> schemas.FaultInjectionOutput:
            request = schemas.InjectFaultInput.model_validate(
                {"vehicle_id": vehicle_id, "fault": fault, "params": params or {}}
            )
            fault_id, impact = fault_capability.inject_fault(
                request.vehicle_id, request.fault, request.params
            )
            now = current_time()
            item = _evaluate(service, request.vehicle_id, as_of=now)
            return schemas.FaultInjectionOutput(
                fault_id=fault_id,
                vehicle_id=request.vehicle_id,
                fault=request.fault,
                expected_quality_impact=impact,
                data_quality=_quality_output(
                    item.data_quality,
                    as_of=now,
                    start=item.points[0].device_time,
                    end=item.latest.device_time,
                ),
            )

        @server.tool(
            name="reset_simulator",
            description="Clear active simulator faults and restore the seeded frames.",
            annotations=_DESTRUCTIVE,
            structured_output=True,
        )
        @_structured_errors
        def reset_simulator(
            fault: schemas.FaultName | None = None,
            vehicle_id: str | None = None,
        ) -> schemas.ResetSimulatorOutput:
            request = schemas.ResetSimulatorInput.model_validate(
                {"fault": fault, "vehicle_id": vehicle_id}
            )
            cleared = fault_capability.reset_simulator(
                fault=request.fault, vehicle_id=request.vehicle_id
            )
            now = current_time()
            fleet = service.evaluate_fleet(as_of=now)
            return schemas.ResetSimulatorOutput(
                reset=True,
                cleared_faults=cleared,
                data_quality=_quality_output(
                    fleet.data_quality,
                    as_of=now,
                    start=min(item.points[0].device_time for item in fleet.vehicles),
                    end=max(item.latest.device_time for item in fleet.vehicles),
                ),
            )

    register_resources(server)
    register_prompts(server)
    for tool_name, input_model in schemas.TOOL_INPUT_MODELS.items():
        tool = server._tool_manager.get_tool(tool_name)
        if tool is not None:
            tool.parameters = input_model.model_json_schema(by_alias=True)
            tool.fn_metadata = tool.fn_metadata.model_copy(update={"arg_model": input_model})
    return server


def _trip_distance(points: tuple[TelemetryPoint, ...]) -> float:
    from math import asin, cos, radians, sin, sqrt

    distance = 0.0
    for first, second in pairwise(points):
        lat1, lat2 = radians(first.latitude), radians(second.latitude)
        value = (
            sin((lat2 - lat1) / 2) ** 2
            + cos(lat1) * cos(lat2) * sin(radians(second.longitude - first.longitude) / 2) ** 2
        )
        distance += 6371 * 2 * asin(sqrt(value))
    return distance
