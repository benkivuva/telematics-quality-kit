"""GT06 login and ACK tests against copied protocol vectors."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from telematics.codecs.crc import crc16_x25
from telematics.codecs.gt06 import GT06Codec
from telematics.errors import ParseError
from telematics.models.telemetry import TelemetryPoint

FIXTURES = Path(__file__).parents[1] / "fixtures"


def read_hex_fixture(name: str) -> bytes:
    lines = (FIXTURES / name).read_text(encoding="utf-8").splitlines()
    return bytes.fromhex(" ".join(line for line in lines if not line.startswith("#")))


@pytest.mark.unit
def test_gt06_login_golden_vector_decodes_expected_fields() -> None:
    codec = GT06Codec()

    login = codec.decode_login(read_hex_fixture("gt06_login.hex"))

    assert login.imei == "123456789012345"
    assert login.serial_number == 1
    assert login.protocol_number == 0x01


@pytest.mark.unit
def test_gt06_login_ack_matches_golden_bytes() -> None:
    codec = GT06Codec()
    login = codec.decode_login(read_hex_fixture("gt06_login.hex"))

    assert codec.encode_login_ack(login.serial_number) == read_hex_fixture("gt06_login_ack.hex")


@pytest.mark.unit
@pytest.mark.parametrize("frame", [b"", b"not a GT06 frame"])
def test_gt06_login_rejects_malformed_frame_with_parse_error(frame: bytes) -> None:
    with pytest.raises(ParseError):
        GT06Codec().decode_login(frame)


@pytest.mark.unit
@pytest.mark.parametrize("frame", [b"\x78\x78\x1f\x12", b"\x00\x00\x1f\x12" + bytes(32)])
def test_gt06_location_rejects_short_or_bad_start_frame(frame: bytes) -> None:
    with pytest.raises(ParseError):
        GT06Codec().decode(frame)


@pytest.mark.unit
def test_gt06_login_rejects_bad_crc_with_parse_error() -> None:
    frame = bytearray(read_hex_fixture("gt06_login.hex"))
    frame[14] ^= 0x01

    with pytest.raises(ParseError):
        GT06Codec().decode_login(bytes(frame))


@pytest.mark.unit
def test_gt06_login_rejects_non_bcd_terminal_id_with_parse_error() -> None:
    frame = bytearray(read_hex_fixture("gt06_login.hex"))
    frame[5] = 0xFA
    frame[14:16] = crc16_x25(bytes(frame[2:14])).to_bytes(2, byteorder="big")

    with pytest.raises(ParseError):
        GT06Codec().decode_login(bytes(frame))


@pytest.mark.unit
def test_gt06_location_encoder_round_trips_with_protocol_quantization() -> None:
    point = TelemetryPoint(
        device_time=datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC),
        latitude=12.5,
        longitude=-45.25,
        speed_kph=18.0,
        course_deg=123,
        satellites=8,
        serial_number=7,
    )
    codec = GT06Codec()

    frame = codec.encode([point])
    decoded = codec.decode(frame)

    assert len(decoded) == 1
    result = decoded[0]
    assert result.device_time == point.device_time
    assert abs(result.latitude - point.latitude) <= 0.5 / 1_800_000
    assert abs(result.longitude - point.longitude) <= 0.5 / 1_800_000
    assert result.speed_kph == point.speed_kph
    assert result.course_deg == point.course_deg
    assert result.satellites == point.satellites
    assert result.serial_number == point.serial_number

    # Independent expectations from §7.1's 1/30000-minute coordinate units.
    assert frame[11:15] == bytes.fromhex("01 57 52 A0")
    assert frame[15:19] == bytes.fromhex("04 DA D4 10")
