"""Deterministic synthetic byte generation tests."""

from datetime import UTC, datetime, timedelta

import pytest

from telematics.backends.simulator import SimulatorBackend
from telematics.clock import ManualClock
from telematics.codecs.gt06 import GT06Codec
from telematics.codecs.teltonika import TeltonikaCodec
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
def test_simulator_backend_routes_frames_through_the_profile_codec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decoded_by_codec: dict[str, list[bytes]] = {"gt06": [], "teltonika": []}
    gt06_decode = GT06Codec.decode
    teltonika_decode = TeltonikaCodec.decode

    def record_gt06_decode(codec: GT06Codec, frame: bytes):
        decoded_by_codec["gt06"].append(frame)
        return gt06_decode(codec, frame)

    def record_teltonika_decode(codec: TeltonikaCodec, frame: bytes):
        decoded_by_codec["teltonika"].append(frame)
        return teltonika_decode(codec, frame)

    monkeypatch.setattr(GT06Codec, "decode", record_gt06_decode)
    monkeypatch.setattr(TeltonikaCodec, "decode", record_teltonika_decode)
    now = datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)
    tap = EventTap()
    events = tap.subscribe(maxsize=64)

    backend = SimulatorBackend(seed=42, clock=ManualClock(now), vehicles=12, event_tap=tap)

    assert len(decoded_by_codec["teltonika"]) == 9
    assert len(decoded_by_codec["gt06"]) == 3
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
        codec = GT06Codec() if vehicle.profile.protocol == "gt06" else TeltonikaCodec()
        decoded = codec.decode(frames[vehicle.vehicle_id])[0]
        assert decoded.speed_kph <= vehicle.profile.max_speed_kph


@pytest.mark.unit
def test_simulator_frames_at_is_deterministic_for_each_tick() -> None:
    start = datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)
    at = start + timedelta(seconds=30)
    first = Simulator(seed=51, clock=ManualClock(start)).frames_at(vehicles=2, at=at, tick_index=1)
    second = Simulator(seed=51, clock=ManualClock(start)).frames_at(vehicles=2, at=at, tick_index=1)

    assert first == second
    assert first != Simulator(seed=51, clock=ManualClock(start)).frames(vehicles=2)


@pytest.mark.unit
def test_backend_advance_emits_profile_cadence_frames_through_decoders() -> None:
    start = datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)
    clock = ManualClock(start)
    backend = SimulatorBackend(seed=41, clock=clock, vehicles=1)

    end = backend.advance(timedelta(seconds=60))

    points = backend.get_points("TRK-0001")
    assert end == start + timedelta(seconds=60)
    assert len(points) == 3
    assert [point.device_time for point in points] == [
        start,
        start + timedelta(seconds=30),
        start + timedelta(seconds=60),
    ]
    assert all(point.received_at is not None for point in points)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("severity", "expected_minutes"),
    [("low", 5), ("medium", 10), ("high", 20)],
)
def test_fault_severity_scales_default_stale_magnitude(
    severity: str, expected_minutes: int
) -> None:
    start = datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)
    backend = SimulatorBackend(seed=42, clock=ManualClock(start), vehicles=1)

    backend.inject_fault("TRK-0001", "stale_device", {"severity": severity})

    assert backend.get_points("TRK-0001")[-1].device_time == start - timedelta(
        minutes=expected_minutes
    )


@pytest.mark.unit
def test_rural_blackout_keeps_last_location_while_time_ages() -> None:
    start = datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)
    clock = ManualClock(start)
    backend = SimulatorBackend(seed=42, clock=clock, vehicles=1)
    initial = backend.get_points("TRK-0001")

    backend.inject_fault("TRK-0001", "rural_blackout", {})
    backend.advance(timedelta(minutes=6))

    assert len(backend.get_points("TRK-0001")) == len(initial)
    assert backend.get_points("TRK-0001")[-1].device_time == start
    assert clock.now() == start + timedelta(minutes=6)


@pytest.mark.unit
def test_fault_duration_expires_and_reporting_resumes() -> None:
    start = datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)
    backend = SimulatorBackend(seed=42, clock=ManualClock(start), vehicles=1)

    backend.inject_fault("TRK-0001", "rural_blackout", {"duration": "1m"})
    backend.advance(timedelta(minutes=1))

    assert not backend._active_faults
    assert backend.get_points("TRK-0001")[-1].device_time == start + timedelta(minutes=1)
