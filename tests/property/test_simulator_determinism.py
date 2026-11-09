"""Seeded fleet frame generation remains byte-deterministic."""

from datetime import UTC, datetime
from hashlib import sha256

import pytest
from hypothesis import given
from hypothesis import strategies as st

from telematics.clock import ManualClock
from telematics.simulator.generator import Simulator


@pytest.mark.property
@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
def test_frame_sha256_is_stable_for_seeded_fleet(seed: int) -> None:
    now = datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)
    first = Simulator(seed=seed, clock=ManualClock(now)).frames(vehicles=12)
    second = Simulator(seed=seed, clock=ManualClock(now)).frames(vehicles=12)

    first_hash = sha256(b"".join(frame for _, frame in first)).digest()
    second_hash = sha256(b"".join(frame for _, frame in second)).digest()
    assert first_hash == second_hash
