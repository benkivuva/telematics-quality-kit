"""Arbitrary bytes produce points or only the documented ParseError."""

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from telematics.codecs.gt06 import GT06Codec
from telematics.codecs.teltonika import TeltonikaCodec
from telematics.errors import ParseError

FIXTURES = Path(__file__).parents[1] / "fixtures"


def read_vector() -> bytes:
    lines = (FIXTURES / "teltonika_codec8.hex").read_text(encoding="utf-8").splitlines()
    return bytes.fromhex(" ".join(line for line in lines if not line.startswith("#")))


@pytest.mark.property
@given(frame=st.binary(max_size=512))
def test_teltonika_decoder_never_leaks_unexpected_exceptions(frame: bytes) -> None:
    try:
        TeltonikaCodec().decode(frame)
    except ParseError:
        pass


@pytest.mark.property
@given(frame=st.binary(max_size=128))
def test_gt06_decoder_never_leaks_unexpected_exceptions(frame: bytes) -> None:
    try:
        GT06Codec().decode(frame)
    except ParseError:
        pass


@pytest.mark.unit
def test_parser_safety_vectors_decode_successfully() -> None:
    assert len(TeltonikaCodec().decode(read_vector())) == 1
