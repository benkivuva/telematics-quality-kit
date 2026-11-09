"""Live text and JSON views over the bounded ingestion event tap."""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from telematics.backends.simulator import SimulatorBackend
from telematics.clock import ManualClock
from telematics.config import FreshnessConfig
from telematics.ingest.events import (
    ChecksEvaluated,
    Decoded,
    FaultCleared,
    FaultInjected,
    FrameReceived,
    ParseFailed,
    PipelineEvent,
    Stored,
    VerdictChanged,
)
from telematics.ingest.tap import EventSubscription, EventTap
from telematics.models.quality import Verdict
from telematics.service.vehicles import VehicleService

Stage = Literal["RX", "DECODE", "STORE", "CHECK", "ISSUE", "PARSE", "VERDICT", "FAULT"]
_STAGES: tuple[Stage, ...] = (
    "RX",
    "DECODE",
    "STORE",
    "CHECK",
    "ISSUE",
    "PARSE",
    "VERDICT",
    "FAULT",
)
_SYMBOLS = {Verdict.PASS: "✓", Verdict.WARN: "⚠", Verdict.BLOCK: "⛔"}


class StreamEvent(BaseModel):
    """Strict JSON representation of one event shown by the CLI stream."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    timestamp: str
    vehicle_id: str
    stage: Stage
    message: str
    details: dict[str, str | int | float | bool] = Field(default_factory=dict)
    priority: bool = False


def is_priority_event(event: PipelineEvent) -> bool:
    """Return true for issue, parse, fault, and verdict-change events."""
    if isinstance(event, (ParseFailed, VerdictChanged, FaultInjected, FaultCleared)):
        return True
    return isinstance(event, ChecksEvaluated) and any(
        result.verdict is not Verdict.PASS for result in event.results
    )


def format_event(
    event: PipelineEvent,
    *,
    at: datetime,
    protocol: str = "",
    show_hex: bool = False,
) -> StreamEvent:
    """Convert one immutable pipeline event into its validated stream model."""
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("stream timestamp must be timezone-aware")
    timestamp = at.astimezone(UTC).isoformat(timespec="milliseconds")
    priority = is_priority_event(event)
    if isinstance(event, FrameReceived):
        frame_hex = event.frame.hex()
        shown_hex = frame_hex if show_hex else f"{frame_hex[:4]}…"
        return StreamEvent(
            timestamp=timestamp,
            vehicle_id=event.vehicle_id,
            stage="RX",
            message="received frame",
            details={"protocol": protocol, "bytes": len(event.frame), "hex": shown_hex},
            priority=priority,
        )
    if isinstance(event, Decoded):
        point = event.points[0] if event.points else None
        details: dict[str, str | int | float | bool] = {"records": len(event.points)}
        if point is not None:
            details.update(
                latitude=point.latitude,
                longitude=point.longitude,
                speed_kph=point.speed_kph,
            )
        return StreamEvent(
            timestamp=timestamp,
            vehicle_id=event.vehicle_id,
            stage="DECODE",
            message=f"decoded {len(event.points)} record(s)",
            details=details,
        )
    if isinstance(event, ParseFailed):
        return StreamEvent(
            timestamp=timestamp,
            vehicle_id=event.vehicle_id,
            stage="PARSE",
            message=f"FAIL · {event.reason}",
            priority=True,
        )
    if isinstance(event, Stored):
        return StreamEvent(
            timestamp=timestamp,
            vehicle_id=event.vehicle_id,
            stage="STORE",
            message="stored point",
            details={"serial_number": event.point.serial_number},
        )
    if isinstance(event, ChecksEvaluated):
        statuses = tuple(
            f"{item.name} {item.verdict.value} {_SYMBOLS[item.verdict]}" for item in event.results
        )
        summary = " · ".join(statuses)
        return StreamEvent(
            timestamp=timestamp,
            vehicle_id=event.vehicle_id,
            stage="ISSUE" if priority else "CHECK",
            message=summary or "no checks returned",
            details={
                "checks": len(event.results),
                "failed": sum(item.verdict is not Verdict.PASS for item in event.results),
            },
            priority=priority,
        )
    if isinstance(event, VerdictChanged):
        before = event.previous.value if event.previous is not None else "—"
        return StreamEvent(
            timestamp=timestamp,
            vehicle_id=event.vehicle_id,
            stage="VERDICT",
            message=f"{before} → {event.current.value} {_SYMBOLS[event.current]}",
            priority=True,
        )
    if isinstance(event, FaultInjected):
        return StreamEvent(
            timestamp=timestamp,
            vehicle_id=event.vehicle_id,
            stage="FAULT",
            message=f"{event.fault}: {event.expected_impact}",
            priority=True,
        )
    if isinstance(event, FaultCleared):
        return StreamEvent(
            timestamp=timestamp,
            vehicle_id=event.vehicle_id,
            stage="FAULT",
            message=f"cleared {event.fault}",
            priority=True,
        )
    raise TypeError(f"unsupported pipeline event: {type(event).__name__}")


class EventSampler:
    """Limit normal event lines while always retaining priority events."""

    def __init__(self, *, rate: int = 20) -> None:
        if rate < 1:
            raise ValueError("stream rate must be positive")
        self._interval = 1.0 / rate
        self._last_normal_at: float | None = None
        self.sampled = 0
        self.normal_seen = 0

    def include(self, event: PipelineEvent, *, now: float) -> bool:
        """Decide whether the event should print at the supplied monotonic time."""
        if is_priority_event(event):
            return True
        self.normal_seen += 1
        if self._last_normal_at is None or now - self._last_normal_at >= self._interval:
            self._last_normal_at = now
            return True
        self.sampled += 1
        return False


def render_line(event: StreamEvent, *, as_json: bool) -> str:
    """Serialize a stream event as one JSON object or a compact terminal line."""
    if as_json:
        return event.model_dump_json()
    clock = datetime.fromisoformat(event.timestamp).strftime("%H:%M:%S.%f")[:-3]
    return f"{clock} {event.vehicle_id:<12} {event.stage:<7} {event.message}"


def drain_subscription(
    subscription: EventSubscription,
    *,
    at: datetime,
    sampler: EventSampler,
    protocol_for: Callable[[str], str],
    stages: set[str] | None = None,
    vehicle_id: str | None = None,
    issues_only: bool = False,
    show_hex: bool = False,
    as_json: bool = False,
    monotonic: Callable[[], float] = time.monotonic,
) -> tuple[str, ...]:
    """Drain ready events without blocking the pipeline producer."""
    output: list[str] = []
    while not subscription.empty():
        event = subscription.get_nowait()
        if vehicle_id is not None and event.vehicle_id != vehicle_id:
            continue
        protocol = protocol_for(event.vehicle_id)
        line = format_event(event, at=at, protocol=str(protocol), show_hex=show_hex)
        if stages is not None and line.stage.lower() not in stages:
            continue
        if issues_only and not line.priority:
            continue
        if sampler.include(event, now=monotonic()):
            output.append(render_line(line, as_json=as_json))
    return tuple(output)


def stream(
    *,
    vehicles: int,
    seed: int,
    rate: int = 20,
    vehicle_id: str | None = None,
    stages: set[str] | None = None,
    issues_only: bool = False,
    show_hex: bool = False,
    as_json: bool = False,
) -> int:
    """Run the embedded simulator and continuously display tapped events."""
    start = datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)
    clock = ManualClock(start)
    tap = EventTap()
    subscription = tap.subscribe(maxsize=256)
    backend = SimulatorBackend(seed=seed, clock=clock, vehicles=vehicles, event_tap=tap)
    service = VehicleService(backend, FreshnessConfig())
    sampler = EventSampler(rate=rate)
    previous: dict[str, Verdict] = {}
    try:
        while True:
            ready: list[PipelineEvent] = []
            while not subscription.empty():
                ready.append(subscription.get_nowait())
            for event in ready:
                if isinstance(event, Stored):
                    summary = service.evaluate_vehicle(event.vehicle_id, as_of=clock.now())
                    checks = ChecksEvaluated(event.vehicle_id, summary.data_quality.checks)
                    ready.append(checks)
                    old = previous.get(event.vehicle_id)
                    current = summary.data_quality.verdict
                    if old is not None and old is not current:
                        ready.append(VerdictChanged(event.vehicle_id, old, current))
                    previous[event.vehicle_id] = current
            for event in ready:
                if vehicle_id is not None and event.vehicle_id != vehicle_id:
                    continue
                line = format_event(
                    event,
                    at=clock.now(),
                    protocol=backend.get_profile(event.vehicle_id).protocol,
                    show_hex=show_hex,
                )
                if stages is not None and line.stage.lower() not in stages:
                    continue
                if issues_only and not line.priority:
                    continue
                if sampler.include(event, now=time.monotonic()):
                    print(render_line(line, as_json=as_json), flush=True)
            backend.advance(timedelta(seconds=1))
            time.sleep(1)
    except KeyboardInterrupt:
        tap.unsubscribe(subscription)
        shown = sampler.normal_seen - sampler.sampled
        print(
            f"-- sampled {shown} of {sampler.normal_seen} normal events; "
            "priority issues retained --",
            file=sys.stderr if as_json else sys.stdout,
        )
    return 0


def add_stream_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the portable ``stream`` subcommand."""
    parser = commands.add_parser("stream", help="follow the embedded pipeline event tap")
    parser.add_argument("--vehicles", type=_positive_vehicles, default=12)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--vehicle")
    parser.add_argument(
        "--stage", action="append", choices=tuple(stage.lower() for stage in _STAGES)
    )
    parser.add_argument("--issues-only", action="store_true")
    parser.add_argument("--hex", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--rate", type=int, default=20)


def _positive_vehicles(value: str) -> int:
    """Validate a stream fleet size."""
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("vehicles must be an integer from 1 to 10000") from exc
    if not 1 <= result <= 10_000:
        raise argparse.ArgumentTypeError("vehicles must be between 1 and 10000")
    return result
