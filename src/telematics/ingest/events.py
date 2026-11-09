"""Immutable event types emitted by the ingestion and quality pipeline."""

from dataclasses import dataclass

from telematics.models.quality import CheckResult, Verdict
from telematics.models.telemetry import TelemetryPoint


@dataclass(frozen=True, slots=True)
class FrameReceived:
    vehicle_id: str
    frame: bytes


@dataclass(frozen=True, slots=True)
class Decoded:
    vehicle_id: str
    points: tuple[TelemetryPoint, ...]


@dataclass(frozen=True, slots=True)
class ParseFailed:
    vehicle_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class Stored:
    vehicle_id: str
    point: TelemetryPoint


@dataclass(frozen=True, slots=True)
class ChecksEvaluated:
    vehicle_id: str
    results: tuple[CheckResult, ...]


@dataclass(frozen=True, slots=True)
class VerdictChanged:
    vehicle_id: str
    previous: Verdict | None
    current: Verdict


@dataclass(frozen=True, slots=True)
class FaultInjected:
    vehicle_id: str
    fault: str
    expected_impact: str


@dataclass(frozen=True, slots=True)
class FaultCleared:
    vehicle_id: str
    fault: str


type PipelineEvent = (
    FrameReceived
    | Decoded
    | ParseFailed
    | Stored
    | ChecksEvaluated
    | VerdictChanged
    | FaultInjected
    | FaultCleared
)
