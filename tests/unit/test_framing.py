"""Protocol stream splitters preserve frames across TCP chunk boundaries."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import pytest
from hypothesis import given
from hypothesis import strategies as st

from telematics.codecs.gt06 import GT06Codec
from telematics.ingest.framing import GT06FrameSplitter, TeltonikaFrameSplitter
from telematics.models.telemetry import TelemetryPoint

FIXTURES = Path(__file__).parents[1] / "fixtures"


class Splitter(Protocol):
    def feed(self, chunk: bytes) -> tuple[bytes, ...]: ...


def read_hex_fixture(name: str) -> bytes:
    lines = (FIXTURES / name).read_text(encoding="utf-8").splitlines()
    return bytes.fromhex(" ".join(line for line in lines if not line.startswith("#")))


def partition(data: bytes, sizes: list[int]) -> list[bytes]:
    chunks: list[bytes] = []
    cursor = 0
    for size in sizes:
        if cursor >= len(data):
            break
        chunks.append(data[cursor : cursor + size])
        cursor += size
    if cursor < len(data):
        chunks.append(data[cursor:])
    return chunks


@pytest.mark.property
@pytest.mark.parametrize(
    ("splitter_factory", "frame_factory"),
    [
        (
            GT06FrameSplitter,
            lambda: GT06Codec().encode(
                (
                    TelemetryPoint(
                        datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC),
                        -1.2921,
                        36.8219,
                        30,
                        90,
                        8,
                        1,
                    ),
                )
            ),
        ),
        (TeltonikaFrameSplitter, lambda: read_hex_fixture("teltonika_codec8.hex")),
    ],
)
@given(st.lists(st.integers(min_value=1, max_value=32), max_size=80))
def test_valid_stream_is_invariant_to_arbitrary_chunking(
    splitter_factory: Callable[[], Splitter],
    frame_factory: Callable[[], bytes],
    sizes: list[int],
) -> None:
    frame = frame_factory()
    stream = frame + frame
    splitter = splitter_factory()

    result: list[bytes] = []
    for chunk in partition(stream, sizes):
        result.extend(splitter.feed(chunk))

    assert result == [frame, frame]


@pytest.mark.unit
def test_teltonika_splitter_discards_garbage_and_resynchronizes() -> None:
    frame = read_hex_fixture("teltonika_codec8.hex")
    splitter = TeltonikaFrameSplitter()

    assert splitter.feed(b"garbage" + frame[:5]) == ()
    assert splitter.feed(frame[5:] + frame) == (frame, frame)
