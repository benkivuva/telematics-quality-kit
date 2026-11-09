"""Golden-vector tests for GT06 CRC-16/X25."""

from pathlib import Path

import pytest

from telematics.codecs.crc import crc16_ibm, crc16_x25

FIXTURES = Path(__file__).parents[1] / "fixtures"


def read_hex_fixture(name: str) -> bytes:
    lines = (FIXTURES / name).read_text(encoding="utf-8").splitlines()
    return bytes.fromhex(" ".join(line for line in lines if not line.startswith("#")))


@pytest.mark.unit
def test_gt06_login_crc_matches_golden_vector() -> None:
    frame = read_hex_fixture("gt06_login.hex")

    assert crc16_x25(frame[2:14]) == 0x8CDD


@pytest.mark.unit
def test_gt06_login_ack_crc_matches_golden_vector() -> None:
    frame = read_hex_fixture("gt06_login_ack.hex")

    assert crc16_x25(frame[2:6]) == 0xD9DC


@pytest.mark.unit
def test_teltonika_codec8_crc_matches_golden_vector_and_differs_from_x25() -> None:
    frame = read_hex_fixture("teltonika_codec8.hex")
    length = int.from_bytes(frame[4:8], byteorder="big")
    crc_input = frame[8 : 8 + length]

    assert length == 54
    assert crc16_ibm(crc_input) == 0xC7CF
    assert crc16_x25(crc_input) == 0x5DAF
