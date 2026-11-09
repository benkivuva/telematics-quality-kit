"""Teltonika Codec 8 golden vector, round-trip, and parser safety tests."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from telematics.codecs.crc import crc16_ibm
from telematics.codecs.teltonika import TeltonikaCodec
from telematics.errors import ParseError
from telematics.models.telemetry import TelemetryPoint

FIXTURES = Path(__file__).parents[1] / "fixtures"


def read_hex_fixture(name: str) -> bytes:
    lines = (FIXTURES / name).read_text(encoding="utf-8").splitlines()
    return bytes.fromhex(" ".join(line for line in lines if not line.startswith("#")))


@pytest.mark.unit
def test_codec8_golden_vector_decodes_expected_location_fields() -> None:
    point = TeltonikaCodec().decode(read_hex_fixture("teltonika_codec8.hex"))[0]

    assert point.device_time == datetime(2019, 6, 10, 10, 4, 46, tzinfo=UTC)
    assert point.latitude == 0.0
    assert point.longitude == 0.0
    assert point.speed_kph == 0.0
    assert point.course_deg == 0
    assert point.satellites == 0


@pytest.mark.unit
def test_codec8_round_trips_multiple_records_with_coordinate_quantization() -> None:
    points = [
        TelemetryPoint(
            device_time=datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC),
            latitude=-1.2921,
            longitude=36.8219,
            speed_kph=62.0,
            course_deg=274,
            satellites=9,
            serial_number=1,
        ),
        TelemetryPoint(
            device_time=datetime(2024, 4, 5, 6, 8, 8, tzinfo=UTC),
            latitude=-1.3,
            longitude=36.9,
            speed_kph=0.0,
            course_deg=0,
            satellites=7,
            serial_number=2,
        ),
    ]

    decoded = TeltonikaCodec().decode(TeltonikaCodec().encode(points))

    assert len(decoded) == 2
    for original, result in zip(points, decoded, strict=True):
        assert result.device_time == original.device_time
        assert abs(result.latitude - original.latitude) <= 0.5e-7
        assert abs(result.longitude - original.longitude) <= 0.5e-7
        assert result.speed_kph == original.speed_kph
        assert result.course_deg == original.course_deg
        assert result.satellites == original.satellites


@pytest.mark.unit
@pytest.mark.parametrize(
    "frame",
    [b"", b"bad frame", bytes.fromhex("0000000000000000080101")],
)
def test_codec8_rejects_malformed_frames_with_parse_error(frame: bytes) -> None:
    with pytest.raises(ParseError):
        TeltonikaCodec().decode(frame)


@pytest.mark.unit
def test_codec8_rejects_crc_corruption_with_parse_error() -> None:
    frame = bytearray(read_hex_fixture("teltonika_codec8.hex"))
    frame[20] ^= 1

    with pytest.raises(ParseError):
        TeltonikaCodec().decode(bytes(frame))


@pytest.mark.unit
def test_codec8_rejects_codec8_extended_as_unsupported() -> None:
    frame = bytearray(read_hex_fixture("teltonika_codec8.hex"))
    frame[8] = 0x8E
    frame[62:66] = crc16_ibm(frame[8:62]).to_bytes(4, "big")

    with pytest.raises(ParseError, match=r"Codec 8 \(0x08\) only"):
        TeltonikaCodec().decode(bytes(frame))
