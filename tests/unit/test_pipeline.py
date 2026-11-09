"""Parser-in-the-loop ingest tests."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta, timezone

import pytest

from telematics.clock import ManualClock
from telematics.codecs.gt06 import GT06Codec
from telematics.errors import ParseError
from telematics.ingest.events import Decoded, FrameReceived, ParseFailed, Stored
from telematics.ingest.pipeline import IngestPipeline
from telematics.models.telemetry import TelemetryPoint
from telematics.store.memory import MemoryPointStore


@pytest.mark.unit
def test_pipeline_decodes_frame_before_storing_point() -> None:
    point = TelemetryPoint(datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC), 12.5, -45.25, 18, 123, 8, 7)
    received_at = datetime(2024, 4, 5, 6, 7, 9, tzinfo=UTC)
    store = MemoryPointStore()
    pipeline = IngestPipeline(GT06Codec(), store, clock=ManualClock(received_at))

    decoded = pipeline.ingest("TRK-0001", GT06Codec().encode((point,)))

    assert len(decoded) == 1
    assert decoded[0].device_time == point.device_time
    assert decoded[0].received_at == received_at
    assert not decoded[0].out_of_order
    assert store.latest("TRK-0001") == decoded[0]


@pytest.mark.unit
def test_pipeline_flags_late_points_without_reordering_or_dropping() -> None:
    codec = GT06Codec()
    received_at = datetime(2024, 4, 5, 6, 8, 0, tzinfo=UTC)
    store = MemoryPointStore()
    pipeline = IngestPipeline(codec, store, clock=ManualClock(received_at))
    later = TelemetryPoint(received_at, 1.0, 2.0, 0, 0, 6, 2)
    earlier = TelemetryPoint(received_at - timedelta(minutes=2), 1.1, 2.1, 0, 0, 6, 1)

    pipeline.ingest("TRK-0001", codec.encode((later,)))
    late = pipeline.ingest("TRK-0001", codec.encode((earlier,)))

    assert late[0].out_of_order
    assert tuple(point.device_time for point in store.points("TRK-0001")) == (
        later.device_time,
        earlier.device_time,
    )


@pytest.mark.unit
def test_pipeline_emits_typed_stage_events_and_parse_failure() -> None:
    from telematics.ingest.tap import EventTap

    tap = EventTap()
    events = tap.subscribe(maxsize=8)
    pipeline = IngestPipeline(
        GT06Codec(),
        MemoryPointStore(),
        clock=ManualClock(datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)),
        event_tap=tap,
    )

    point = TelemetryPoint(datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC), 12.5, -45.25, 18, 123, 8, 7)
    frame = GT06Codec().encode((point,))
    pipeline.ingest("TRK-0001", frame)
    received, decoded, stored = (events.get_nowait() for _ in range(3))
    assert isinstance(received, FrameReceived)
    assert isinstance(decoded, Decoded)
    assert isinstance(stored, Stored)

    with pytest.raises(ParseError):
        pipeline.ingest("TRK-0001", b"invalid")
    assert isinstance(events.get_nowait(), FrameReceived)
    assert isinstance(events.get_nowait(), ParseFailed)


@pytest.mark.unit
def test_pipeline_normalizes_device_time_to_utc() -> None:
    local_time = datetime(2024, 4, 5, 9, 7, 8, tzinfo=timezone(timedelta(hours=3)))
    point = TelemetryPoint(local_time, 1.0, 2.0, 10, 45, 7, 1)

    class FixedCodec:
        def decode(self, frame: bytes) -> list[TelemetryPoint]:
            return [point]

        def encode(self, points: Sequence[TelemetryPoint]) -> bytes:
            raise NotImplementedError

    pipeline = IngestPipeline(
        FixedCodec(),
        MemoryPointStore(),
        clock=ManualClock(datetime(2024, 4, 5, 10, 0, tzinfo=UTC)),
    )

    result = pipeline.ingest("TRK-0001", b"valid by test codec")[0]

    assert result.device_time == datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)


@pytest.mark.unit
def test_pipeline_rejects_out_of_range_decoded_coordinates() -> None:
    point = TelemetryPoint(datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC), 91.0, 2.0, 0, 0, 7, 1)

    class InvalidCodec:
        def decode(self, frame: bytes) -> list[TelemetryPoint]:
            return [point]

        def encode(self, points: Sequence[TelemetryPoint]) -> bytes:
            raise NotImplementedError

    pipeline = IngestPipeline(
        InvalidCodec(),
        MemoryPointStore(),
        clock=ManualClock(datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)),
    )

    with pytest.raises(ParseError):
        pipeline.ingest("TRK-0001", b"invalid normalized location")
