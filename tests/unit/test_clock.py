"""Deterministic, explicitly advanced simulator clock tests."""

from datetime import UTC, datetime, timedelta

import pytest

from telematics.clock import ManualClock


@pytest.mark.unit
def test_manual_clock_returns_injected_time_and_advances_deterministically() -> None:
    start = datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)
    clock = ManualClock(start)

    assert clock.now() == start
    assert clock.advance(timedelta(seconds=61)) == datetime(2024, 4, 5, 6, 8, 9, tzinfo=UTC)


@pytest.mark.unit
def test_manual_clock_rejects_backward_advance() -> None:
    clock = ManualClock(datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC))

    with pytest.raises(ValueError, match="cannot move backwards"):
        clock.advance(timedelta(seconds=-1))
