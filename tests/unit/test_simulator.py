"""Deterministic synthetic byte generation tests."""

from datetime import UTC, datetime

import pytest

from telematics.backends.simulator import SimulatorBackend
from telematics.clock import ManualClock
from telematics.codecs.gt06 import GT06Codec
from telematics.ingest.events import Decoded, FrameReceived, Stored
from telematics.ingest.tap import EventTap
from telematics.simulator.generator import Simulator


@pytest.mark.unit
def test_same_seed_and_clock_generate_identical_frames() -> None:
    now = datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)
    first = Simulator(seed=42, clock=ManualClock(now)).frames(vehicles=2)
    second = Simulator(seed=42, clock=ManualClock(now)).frames(vehicles=2)

    assert first == second
    assert [vehicle_id for vehicle_id, _ in first] == ["TRK-0001", "LRY-0001"]


@pytest.mark.unit
@pytest.mark.parametrize("vehicles", [1, 12, 5000])
def test_scaled_fleet_ids_and_imes_are_unique_and_repeatable(vehicles: int) -> None:
    now = datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)
    first = Simulator(seed=42, clock=ManualClock(now)).vehicles(vehicles=vehicles)
    second = Simulator(seed=42, clock=ManualClock(now)).vehicles(vehicles=vehicles)

    assert first == second
    assert len({vehicle.vehicle_id for vehicle in first}) == vehicles
    assert len({vehicle.imei for vehicle in first}) == vehicles
    assert all(vehicle.imei.startswith("000") for vehicle in first)


@pytest.mark.unit
def test_simulator_backend_sends_synthetic_frames_through_gt06_decoder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decoded_frames: list[bytes] = []
    decode = GT06Codec.decode

    def record_decode(codec: GT06Codec, frame: bytes):
        decoded_frames.append(frame)
        return decode(codec, frame)

    monkeypatch.setattr(GT06Codec, "decode", record_decode)
    now = datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)
    tap = EventTap()
    events = tap.subscribe(maxsize=64)

    backend = SimulatorBackend(seed=42, clock=ManualClock(now), vehicles=12, event_tap=tap)

    assert len(decoded_frames) == 12
    assert len(backend.list_vehicle_ids()) == 12
    assert all(backend.get_points(vehicle_id) for vehicle_id in backend.list_vehicle_ids())
    published = tuple(events.get_nowait() for _ in range(36))
    assert sum(isinstance(event, FrameReceived) for event in published) == 12
    assert sum(isinstance(event, Decoded) for event in published) == 12
    assert sum(isinstance(event, Stored) for event in published) == 12


@pytest.mark.unit
def test_generated_frames_respect_each_profile_speed_limit() -> None:
    now = datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)
    simulator = Simulator(
        seed=42,
        clock=ManualClock(now),
        profile_mix={"trk": 25, "lry": 25, "car": 25, "pik": 25},
    )
    fleet = simulator.vehicles(vehicles=4)
    frames = dict(simulator.frames(vehicles=4))

    for vehicle in fleet:
        decoded = GT06Codec().decode(frames[vehicle.vehicle_id])[0]
        assert decoded.speed_kph <= vehicle.profile.max_speed_kph
