"""Shared protocol for binary telematics codecs."""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from telematics.models.telemetry import TelemetryPoint


@runtime_checkable
class Codec(Protocol):
    """Decode a wire frame into points and encode points as a wire frame."""

    def decode(self, frame: bytes) -> list[TelemetryPoint]: ...

    def encode(self, points: Sequence[TelemetryPoint]) -> bytes: ...
