"""Protocol-decoding ingestion path for raw device frames."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from math import isfinite

from telematics.clock import Clock
from telematics.codecs.base import Codec
from telematics.errors import ParseError
from telematics.ingest.events import Decoded, FrameReceived, ParseFailed, PipelineEvent, Stored
from telematics.ingest.tap import EventTap
from telematics.models.telemetry import TelemetryPoint
from telematics.store.base import PointStore


class IngestPipeline:
    """Decode frames before making normalized points available to quality checks."""

    def __init__(
        self,
        codec: Codec,
        store: PointStore,
        *,
        clock: Clock,
        event_tap: EventTap | None = None,
    ) -> None:
        self._codec = codec
        self._store = store
        self._clock = clock
        self._event_tap = event_tap if event_tap is not None else EventTap()

    @property
    def event_tap(self) -> EventTap:
        """Event stream for subscribers observing this pipeline."""
        return self._event_tap

    def ingest(
        self,
        vehicle_id: str,
        frame: bytes,
        *,
        received_at: datetime | None = None,
    ) -> Sequence[TelemetryPoint]:
        self._publish(FrameReceived(vehicle_id, frame))
        try:
            decoded = self._codec.decode(frame)
            receive_time = received_at if received_at is not None else self._clock.now()
            if receive_time.tzinfo is None or receive_time.utcoffset() is None:
                raise ValueError("server receive time must be timezone-aware")
            points = self._normalize(vehicle_id, decoded, receive_time.astimezone(UTC))
        except ParseError as exc:
            self._publish(ParseFailed(vehicle_id, str(exc)))
            raise
        self._publish(Decoded(vehicle_id, tuple(points)))
        for point in points:
            self._store.append(vehicle_id, point)
            self._publish(Stored(vehicle_id, point))
        return tuple(points)

    def _normalize(
        self,
        vehicle_id: str,
        points: Sequence[TelemetryPoint],
        received_at: datetime,
    ) -> list[TelemetryPoint]:
        previous = self._store.points(vehicle_id)
        latest_time = max((point.device_time for point in previous), default=None)
        normalized: list[TelemetryPoint] = []
        for point in points:
            if point.device_time.tzinfo is None or point.device_time.utcoffset() is None:
                raise ParseError("device timestamp must be timezone-aware")
            device_time = point.device_time.astimezone(UTC)
            if (
                not isfinite(point.latitude)
                or not -90 <= point.latitude <= 90
                or not isfinite(point.longitude)
                or not -180 <= point.longitude <= 180
            ):
                raise ParseError("decoded coordinates are out of range")
            if not isfinite(point.speed_kph) or point.speed_kph < 0:
                raise ParseError("decoded speed is invalid")
            late = latest_time is not None and device_time < latest_time
            normalized.append(
                replace(
                    point,
                    device_time=device_time,
                    received_at=received_at,
                    out_of_order=point.out_of_order or late,
                )
            )
            if latest_time is None or device_time > latest_time:
                latest_time = device_time
        return normalized

    def _publish(self, event: PipelineEvent) -> None:
        self._event_tap.publish(event)
