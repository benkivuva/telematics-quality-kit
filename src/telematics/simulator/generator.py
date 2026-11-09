"""Seeded synthetic telematics fleet and encoded device frames."""

import random
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from telematics.clock import Clock
from telematics.codecs.base import Codec
from telematics.codecs.gt06 import GT06Codec
from telematics.codecs.teltonika import TeltonikaCodec
from telematics.models.telemetry import TelemetryPoint
from telematics.simulator.identity import synthetic_imei
from telematics.simulator.profiles import PROFILES, VehicleProfile, assign_profiles


@dataclass(frozen=True, slots=True)
class SimulatedVehicle:
    """Synthetic fleet identity and its operating profile."""

    vehicle_id: str
    imei: str
    profile: VehicleProfile


class Simulator:
    """Generate deterministic device frames from a master seed and injected clock."""

    def __init__(
        self,
        *,
        seed: int,
        clock: Clock,
        profile_mix: Mapping[str, int] | None = None,
    ) -> None:
        self._seed = seed
        self._clock = clock
        self._profile_mix = profile_mix
        self._codecs: Mapping[str, Codec] = {
            "gt06": GT06Codec(),
            "teltonika": TeltonikaCodec(),
        }

    def vehicles(self, *, vehicles: int) -> tuple[SimulatedVehicle, ...]:
        """Build synthetic identities with unique global-index IMEIs."""
        codes = assign_profiles(vehicles, self._profile_mix)
        profile_counts: dict[str, int] = {code: 0 for code in PROFILES}
        fleet: list[SimulatedVehicle] = []
        for global_index, code in enumerate(codes, start=1):
            profile_counts[code] += 1
            fleet.append(
                SimulatedVehicle(
                    vehicle_id=f"{code.upper()}-{profile_counts[code]:04d}",
                    imei=synthetic_imei(global_index),
                    profile=PROFILES[code],
                )
            )
        return tuple(fleet)

    def frames(self, *, vehicles: int) -> tuple[tuple[str, bytes], ...]:
        """Generate one hand-encoded wire frame for each synthetic vehicle."""
        return self.frames_at(vehicles=vehicles, at=self._clock.now(), tick_index=0)

    def frames_at(
        self, *, vehicles: int, at: datetime, tick_index: int
    ) -> tuple[tuple[str, bytes], ...]:
        """Generate deterministic frames for one explicitly indexed simulator tick."""
        fleet = self.vehicles(vehicles=vehicles)
        timestamp = at
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("simulator clock must return a timezone-aware time")
        if tick_index < 0:
            raise ValueError("tick index cannot be negative")
        result: list[tuple[str, bytes]] = []
        for global_index, vehicle in enumerate(fleet, start=1):
            profile = vehicle.profile
            seed_material = f"{self._vehicle_seed(vehicle, global_index)}:{tick_index}".encode()
            tick_seed = int.from_bytes(sha256(seed_material).digest()[:8], "big")
            rng = random.Random(tick_seed)
            point = TelemetryPoint(
                device_time=timestamp,
                latitude=-1.2921 + rng.uniform(-0.01, 0.01),
                longitude=36.8219 + rng.uniform(-0.01, 0.01),
                speed_kph=round(rng.uniform(0, profile.max_speed_kph)),
                course_deg=rng.randrange(360),
                satellites=rng.randrange(5, 13),
                serial_number=global_index,
            )
            codec = self._codecs[profile.protocol]
            result.append((vehicle.vehicle_id, codec.encode((point,))))
        return tuple(result)

    def _vehicle_seed(self, vehicle: SimulatedVehicle, global_index: int) -> int:
        material = f"{self._seed}:{global_index}:{vehicle.imei}:{vehicle.profile.code}".encode()
        return int.from_bytes(sha256(material).digest()[:8], "big")
