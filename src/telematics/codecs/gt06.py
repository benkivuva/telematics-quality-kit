"""GT06 login frame decoding and login acknowledgements."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite

from telematics.codecs.crc import crc16_x25
from telematics.errors import ParseError
from telematics.models.telemetry import TelemetryPoint

_START = b"\x78\x78"
_STOP = b"\x0d\x0a"
_LOGIN_PROTOCOL = 0x01
_LOGIN_LENGTH = 0x0D
_LOCATION_PROTOCOL = 0x12
_LOCATION_LENGTH = 0x1F
_COORDINATE_UNITS_PER_DEGREE = 1_800_000


@dataclass(frozen=True, slots=True)
class GT06Login:
    """Decoded fields from a standard GT06 login packet."""

    imei: str
    serial_number: int
    protocol_number: int


class GT06Codec:
    """Decode standard GT06 login and location frames and encode their pair."""

    def decode(self, frame: bytes) -> list[TelemetryPoint]:
        """Decode a supported GT06 telemetry frame into normalized points."""
        if len(frame) < 4:
            raise ParseError("GT06 frame is too short")
        if frame[3] != _LOCATION_PROTOCOL:
            raise ParseError("unsupported GT06 telemetry protocol number")
        return [self._decode_location(frame)]

    @staticmethod
    def _decode_location(frame: bytes) -> TelemetryPoint:
        if len(frame) < 5:
            raise ParseError("GT06 frame is too short")
        if frame[:2] != _START:
            raise ParseError("invalid GT06 start marker")
        if frame[2] != _LOCATION_LENGTH or len(frame) != _LOCATION_LENGTH + 5:
            raise ParseError("invalid GT06 location length")
        if frame[-2:] != _STOP:
            raise ParseError("invalid GT06 stop marker")
        if frame[3] != _LOCATION_PROTOCOL:
            raise ParseError("unsupported GT06 protocol number for location")

        expected_crc = int.from_bytes(frame[-4:-2], byteorder="big")
        if crc16_x25(frame[2:-4]) != expected_crc:
            raise ParseError("invalid GT06 CRC-16/X25")

        gps_info = frame[10]
        if gps_info >> 4 != 12:
            raise ParseError("invalid GT06 GPS information length")

        latitude_units = int.from_bytes(frame[11:15], byteorder="big")
        longitude_units = int.from_bytes(frame[15:19], byteorder="big")
        if latitude_units > 162_000_000 or longitude_units > 324_000_000:
            raise ParseError("GT06 coordinates are out of range")

        course_status = int.from_bytes(frame[20:22], byteorder="big")
        course_deg = ((course_status >> 8) & 0x03) << 8 | (course_status & 0xFF)
        if course_deg > 360:
            raise ParseError("GT06 course is out of range")

        year, month, day, hour, minute, second = frame[4:10]
        try:
            device_time = datetime(
                2000 + year,
                month,
                day,
                hour,
                minute,
                second,
                tzinfo=UTC,
            )
        except ValueError as exc:
            raise ParseError("invalid GT06 device timestamp") from exc

        latitude = latitude_units / _COORDINATE_UNITS_PER_DEGREE
        longitude = longitude_units / _COORDINATE_UNITS_PER_DEGREE
        if not course_status & 0x0400:
            latitude = -latitude
        if course_status & 0x0800:
            longitude = -longitude

        return TelemetryPoint(
            device_time=device_time,
            latitude=latitude,
            longitude=longitude,
            speed_kph=float(frame[19]),
            course_deg=course_deg,
            satellites=gps_info & 0x0F,
            serial_number=int.from_bytes(frame[30:32], byteorder="big"),
        )

    def encode(self, points: Sequence[TelemetryPoint]) -> bytes:
        """Encode one GT06 location point as a standard 0x12 frame."""
        if len(points) != 1:
            raise ValueError("a GT06 location frame encodes exactly one point")
        point = points[0]
        timestamp = point.device_time
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("GT06 device time must be timezone-aware")
        timestamp = timestamp.astimezone(UTC)
        if not 2000 <= timestamp.year <= 2099:
            raise ValueError("GT06 location year must be from 2000 through 2099")
        if not isfinite(point.latitude) or not -90 <= point.latitude <= 90:
            raise ValueError("GT06 latitude must be finite and within [-90, 90]")
        if not isfinite(point.longitude) or not -180 <= point.longitude <= 180:
            raise ValueError("GT06 longitude must be finite and within [-180, 180]")
        if not 0 <= point.speed_kph <= 255 or not isfinite(point.speed_kph):
            raise ValueError("GT06 speed must be finite and fit in one byte")
        if not 0 <= point.course_deg <= 360:
            raise ValueError("GT06 course must be between 0 and 360 degrees")
        if not 0 <= point.satellites <= 15:
            raise ValueError("GT06 satellite count must fit in one nibble")
        if not 0 <= point.serial_number <= 0xFFFF:
            raise ValueError("GT06 serial number must fit in 16 bits")

        latitude_units = round(abs(point.latitude) * _COORDINATE_UNITS_PER_DEGREE)
        longitude_units = round(abs(point.longitude) * _COORDINATE_UNITS_PER_DEGREE)
        course_status = 0x1000
        if point.latitude >= 0:
            course_status |= 0x0400
        if point.longitude < 0:
            course_status |= 0x0800
        course_status |= point.course_deg

        gps_payload = bytes(
            (
                timestamp.year - 2000,
                timestamp.month,
                timestamp.day,
                timestamp.hour,
                timestamp.minute,
                timestamp.second,
                0xC0 | point.satellites,
            )
        )
        gps_payload += latitude_units.to_bytes(4, byteorder="big")
        gps_payload += longitude_units.to_bytes(4, byteorder="big")
        gps_payload += bytes((round(point.speed_kph),))
        gps_payload += course_status.to_bytes(2, byteorder="big")

        # Synthetic LBS values keep this packet structurally complete without
        # introducing a real network or location identity into test data.
        lbs_payload = b"\x00\x01\x01\x00\x01\x00\x00\x01"
        serial = point.serial_number.to_bytes(2, byteorder="big")
        packet_without_crc = bytes((_LOCATION_PROTOCOL,)) + gps_payload + lbs_payload + serial
        packet_length = len(packet_without_crc) + 2
        checksum_input = bytes((packet_length,)) + packet_without_crc
        checksum = crc16_x25(checksum_input).to_bytes(2, byteorder="big")
        return _START + checksum_input + checksum + _STOP

    @staticmethod
    def decode_login(frame: bytes) -> GT06Login:
        """Decode a standard 0x7878 GT06 login frame."""
        if len(frame) < 5:
            raise ParseError("GT06 frame is too short")
        if frame[:2] != _START:
            raise ParseError("invalid GT06 start marker")

        declared_length = frame[2]
        if declared_length != _LOGIN_LENGTH or len(frame) != declared_length + 5:
            raise ParseError("invalid GT06 login length")
        if frame[-2:] != _STOP:
            raise ParseError("invalid GT06 stop marker")

        protocol_number = frame[3]
        if protocol_number != _LOGIN_PROTOCOL:
            raise ParseError("unsupported GT06 protocol number for login")

        expected_crc = int.from_bytes(frame[-4:-2], byteorder="big")
        if crc16_x25(frame[2:-4]) != expected_crc:
            raise ParseError("invalid GT06 CRC-16/X25")

        terminal_id = frame[4:12]
        nibbles = (nibble for byte in terminal_id for nibble in (byte >> 4, byte & 0x0F))
        if terminal_id[0] >> 4 != 0 or any(nibble > 9 for nibble in nibbles):
            raise ParseError("invalid GT06 BCD terminal ID")
        bcd_digits = "".join(f"{byte >> 4}{byte & 0x0F}" for byte in terminal_id)

        serial_number = int.from_bytes(frame[12:14], byteorder="big")
        return GT06Login(
            imei=bcd_digits[1:],
            serial_number=serial_number,
            protocol_number=protocol_number,
        )

    @staticmethod
    def encode_login_ack(serial_number: int) -> bytes:
        """Encode a GT06 login ACK echoing the request serial number."""
        if not 0 <= serial_number <= 0xFFFF:
            raise ValueError("GT06 serial number must fit in 16 bits")

        packet_without_crc = bytes((_LOGIN_PROTOCOL,)) + serial_number.to_bytes(2, byteorder="big")
        packet_length = len(packet_without_crc) + 2
        checksum_input = bytes((packet_length,)) + packet_without_crc
        checksum = crc16_x25(checksum_input).to_bytes(2, byteorder="big")
        return _START + checksum_input + checksum + _STOP
