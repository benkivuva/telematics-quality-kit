"""Seeded synthetic telematics fleet and encoded device frames."""

import random
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from math import asin, atan2, cos, degrees, radians, sin

from telematics.clock import Clock
from telematics.codecs.base import Codec
from telematics.codecs.gt06 import GT06Codec
from telematics.codecs.teltonika import TeltonikaCodec
from telematics.models.telemetry import TelemetryPoint
from telematics.simulator.identity import synthetic_imei
from telematics.simulator.profiles import PROFILES, VehicleProfile, assign_profiles

_EARTH_RADIUS_KM = 6371.0
_PROFILE_ANCHORS = {
    "trk": (-2.5, 37.5),
    "lry": (-1.2921, 36.8219),
    "car": (-1.2921, 36.8219),
    "pik": (0.5143, 35.2698),
}


@dataclass(frozen=True, slots=True)
class SimulatedVehicle:
    """Synthetic fleet identity and its operating profile."""

    vehicle_id: str
    imei: str
    profile: VehicleProfile


@dataclass(frozen=True, slots=True)
class _Route:
    """One vehicle's deterministic course, speed, and starting point."""

    start_latitude: float
    start_longitude: float
    course_deg: int
    speed_kph: float


def _destination(
    latitude: float, longitude: float, bearing_deg: float, distance_km: float
) -> tuple[float, float]:
    """Return the point reached by travelling ``distance_km`` on a bearing."""
    angular_distance = distance_km / _EARTH_RADIUS_KM
    bearing = radians(bearing_deg)
    lat1, lon1 = radians(latitude), radians(longitude)
    lat2 = asin(
        sin(lat1) * cos(angular_distance) + cos(lat1) * sin(angular_distance) * cos(bearing)
    )
    lon2 = lon1 + atan2(
        sin(bearing) * sin(angular_distance) * cos(lat1),
        cos(angular_distance) - sin(lat1) * sin(lat2),
    )
    return degrees(lat2), degrees(lon2)


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
        self._epoch = clock.now()
        if self._epoch.tzinfo is None or self._epoch.utcoffset() is None:
            raise ValueError("simulator clock must return a timezone-aware time")
        self._routes: dict[str, _Route] = {}

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
        """Generate deterministic route frames for one explicitly indexed tick."""
        fleet = self.vehicles(vehicles=vehicles)
        timestamp = at
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("simulator clock must return a timezone-aware time")
        if tick_index < 0:
            raise ValueError("tick index cannot be negative")
        elapsed_seconds = max(0.0, (timestamp - self._epoch).total_seconds())
        result: list[tuple[str, bytes]] = []
        for global_index, vehicle in enumerate(fleet, start=1):
            profile = vehicle.profile
            route = self._route(vehicle, global_index)
            seed_material = f"{self._vehicle_seed(vehicle, global_index)}:{tick_index}".encode()
            tick_seed = int.from_bytes(sha256(seed_material).digest()[:8], "big")
            rng = random.Random(tick_seed)
            distance_km = route.speed_kph * elapsed_seconds / 3600.0
            latitude, longitude = _destination(
                route.start_latitude, route.start_longitude, route.course_deg, distance_km
            )
            point = TelemetryPoint(
                device_time=timestamp,
                latitude=latitude,
                longitude=longitude,
                speed_kph=route.speed_kph,
                course_deg=route.course_deg,
                satellites=rng.randrange(5, 13),
                serial_number=global_index,
            )
            codec = self._codecs[profile.protocol]
            result.append((vehicle.vehicle_id, codec.encode((point,))))
        return tuple(result)

    def _route(self, vehicle: SimulatedVehicle, global_index: int) -> _Route:
        """Return the cached deterministic route for one synthetic vehicle."""
        route = self._routes.get(vehicle.vehicle_id)
        if route is None:
            anchor_latitude, anchor_longitude = _PROFILE_ANCHORS[vehicle.profile.code]
            rng = random.Random(self._vehicle_seed(vehicle, global_index))
            route = _Route(
                start_latitude=anchor_latitude + rng.uniform(-0.05, 0.05),
                start_longitude=anchor_longitude + rng.uniform(-0.05, 0.05),
                course_deg=rng.randrange(360),
                speed_kph=round(rng.uniform(0.5, 0.95) * vehicle.profile.max_speed_kph, 1),
            )
            self._routes[vehicle.vehicle_id] = route
        return route

    def _vehicle_seed(self, vehicle: SimulatedVehicle, global_index: int) -> int:
        material = f"{self._seed}:{global_index}:{vehicle.imei}:{vehicle.profile.code}".encode()
        return int.from_bytes(sha256(material).digest()[:8], "big")
