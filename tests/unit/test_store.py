"""Bounded append-order retention tests for the in-memory point store."""

from datetime import UTC, datetime, timedelta

import pytest

from telematics.models.telemetry import TelemetryPoint
from telematics.store.memory import MemoryPointStore


def point(device_time: datetime, received_at: datetime) -> TelemetryPoint:
    return TelemetryPoint(
        device_time=device_time,
        latitude=1.0,
        longitude=2.0,
        speed_kph=0,
        course_deg=0,
        satellites=7,
        serial_number=1,
        received_at=received_at,
    )


@pytest.mark.unit
def test_memory_store_prunes_by_receive_time_and_hard_point_limit() -> None:
    origin = datetime(2024, 4, 5, 6, 0, tzinfo=UTC)
    store = MemoryPointStore(retention=timedelta(minutes=1), max_points_per_vehicle=2)

    for index in range(4):
        store.append(
            "TRK-0001",
            point(origin + timedelta(seconds=index), origin + timedelta(seconds=30 * index)),
        )

    retained = store.points("TRK-0001")
    assert len(retained) == 2
    assert retained[0].received_at == origin + timedelta(seconds=60)
    assert retained[1].received_at == origin + timedelta(seconds=90)


@pytest.mark.unit
def test_memory_store_retains_out_of_order_device_time_in_append_order() -> None:
    origin = datetime(2024, 4, 5, 6, 0, tzinfo=UTC)
    store = MemoryPointStore()
    newest = point(origin + timedelta(seconds=10), origin)
    late = point(origin, origin + timedelta(seconds=1))

    store.append("TRK-0001", newest)
    store.append("TRK-0001", late)

    assert store.points("TRK-0001") == (newest, late)
