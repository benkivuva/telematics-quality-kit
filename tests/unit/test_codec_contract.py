"""Both wire codecs implement the shared encode/decode contract."""

from datetime import UTC, datetime

import pytest

from telematics.codecs.base import Codec
from telematics.codecs.gt06 import GT06Codec
from telematics.codecs.teltonika import TeltonikaCodec
from telematics.models.telemetry import TelemetryPoint


@pytest.mark.unit
@pytest.mark.parametrize("codec", [GT06Codec(), TeltonikaCodec()])
def test_gt06_and_teltonika_satisfy_codec_protocol(codec: Codec) -> None:
    assert isinstance(codec, Codec)
    point = TelemetryPoint(
        device_time=datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC),
        latitude=-1.2921,
        longitude=36.8219,
        speed_kph=42.0,
        course_deg=90,
        satellites=8,
        serial_number=7,
    )

    decoded = codec.decode(codec.encode((point,)))

    assert len(decoded) == 1
    assert decoded[0].device_time == point.device_time
