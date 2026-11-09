"""Hand-written Teltonika Codec 8 AVL packet codec."""

import struct
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from telematics.codecs.crc import crc16_ibm
from telematics.errors import ParseError
from telematics.models.telemetry import TelemetryPoint

_PREAMBLE = b"\x00\x00\x00\x00"
_CODEC_ID = 0x08
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_GPS_STRUCT = struct.Struct(">iiHHBH")


class TeltonikaCodec:
    """Encode and decode standard Teltonika Codec 8 packets (ID 0x08)."""

    def decode(self, frame: bytes) -> list[TelemetryPoint]:
        """Decode one complete TCP AVL packet; malformed input raises ParseError."""
        try:
            return self._decode(frame)
        except ParseError:
            raise
        except (IndexError, OverflowError, struct.error, ValueError) as exc:
            raise ParseError("malformed Teltonika Codec 8 frame") from exc

    @staticmethod
    def _decode(frame: bytes) -> list[TelemetryPoint]:
        if len(frame) < 12 or frame[:4] != _PREAMBLE:
            raise ParseError("invalid Teltonika preamble or truncated frame")
        data_length = int.from_bytes(frame[4:8], "big")
        expected_length = 8 + data_length + 4
        if data_length < 2 or len(frame) != expected_length:
            raise ParseError("invalid Teltonika data length")
        data_end = 8 + data_length
        data = frame[8:data_end]
        if int.from_bytes(frame[data_end:], "big") != crc16_ibm(data):
            raise ParseError("invalid Teltonika CRC-16/IBM")
        if data[0] != _CODEC_ID:
            raise ParseError("unsupported Teltonika codec; Codec 8 (0x08) only")
        record_count = data[1]
        cursor = 2
        points: list[TelemetryPoint] = []
        for record_index in range(record_count):
            point, cursor = TeltonikaCodec._decode_record(data, cursor, record_index + 1)
            points.append(point)
        if cursor >= len(data) or data[cursor] != record_count or cursor + 1 != len(data):
            raise ParseError("Teltonika record counts do not match or packet has trailing bytes")
        return points

    @staticmethod
    def _decode_record(data: bytes, cursor: int, serial: int) -> tuple[TelemetryPoint, int]:
        if cursor + 24 > len(data):
            raise ParseError("truncated Teltonika AVL record")
        timestamp_ms = int.from_bytes(data[cursor : cursor + 8], "big")
        cursor += 8
        cursor += 1  # priority
        longitude_i, latitude_i, _altitude, angle, satellites, speed = _GPS_STRUCT.unpack_from(
            data, cursor
        )
        cursor += _GPS_STRUCT.size
        cursor = TeltonikaCodec._skip_io(data, cursor)
        try:
            device_time = _EPOCH + timedelta(milliseconds=timestamp_ms)
        except OverflowError as exc:
            raise ParseError("Teltonika timestamp is out of range") from exc
        return (
            TelemetryPoint(
                device_time=device_time,
                latitude=latitude_i / 10_000_000,
                longitude=longitude_i / 10_000_000,
                speed_kph=float(speed),
                course_deg=angle,
                satellites=satellites,
                serial_number=serial,
            ),
            cursor,
        )

    @staticmethod
    def _skip_io(data: bytes, cursor: int) -> int:
        if cursor + 2 > len(data):
            raise ParseError("truncated Teltonika IO header")
        cursor += 1  # event IO ID
        total_count = data[cursor]
        cursor += 1
        decoded_count = 0
        for width in (1, 2, 4, 8):
            if cursor >= len(data):
                raise ParseError("truncated Teltonika IO group count")
            group_count = data[cursor]
            cursor += 1
            decoded_count += group_count
            group_size = 1 + width
            end = cursor + group_count * group_size
            if end > len(data):
                raise ParseError("truncated Teltonika IO values")
            cursor = end
        if decoded_count != total_count:
            raise ParseError("Teltonika total IO count does not match group counts")
        return cursor

    def encode(self, points: Sequence[TelemetryPoint]) -> bytes:
        """Encode one or more points into a Codec 8 TCP packet."""
        if not 1 <= len(points) <= 0xFF:
            raise ValueError("Codec 8 packets require 1 to 255 records")
        records = b"".join(self._encode_record(point) for point in points)
        data = bytes((_CODEC_ID, len(points))) + records + bytes((len(points),))
        frame = _PREAMBLE + len(data).to_bytes(4, "big") + data
        return frame + crc16_ibm(data).to_bytes(4, "big")

    @staticmethod
    def _encode_record(point: TelemetryPoint) -> bytes:
        if point.device_time.tzinfo is None or point.device_time.utcoffset() is None:
            raise ValueError("Teltonika device time must be timezone-aware")
        timestamp = point.device_time.astimezone(UTC)
        timestamp_ms = int((timestamp - _EPOCH).total_seconds() * 1000)
        if not 0 <= timestamp_ms <= 0xFFFFFFFFFFFFFFFF:
            raise ValueError("Teltonika timestamp must fit in 64 bits")
        if not -180 <= point.longitude <= 180 or not -90 <= point.latitude <= 90:
            raise ValueError("Teltonika coordinates are out of range")
        if not 0 <= point.course_deg <= 360 or not 0 <= point.satellites <= 255:
            raise ValueError("Teltonika angle or satellite count is out of range")
        if not 0 <= point.speed_kph <= 0xFFFF:
            raise ValueError("Teltonika speed must fit in 16 bits")
        gps = _GPS_STRUCT.pack(
            round(point.longitude * 10_000_000),
            round(point.latitude * 10_000_000),
            0,
            point.course_deg,
            point.satellites,
            round(point.speed_kph),
        )
        io = b"\x00\x00\x00\x00\x00\x00"
        return timestamp_ms.to_bytes(8, "big") + b"\x01" + gps + io
