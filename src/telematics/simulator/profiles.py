"""Synthetic Kenya fleet profiles and deterministic mix allocation."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class VehicleProfile:
    """A configurable synthetic operating profile; values are heuristics."""

    code: str
    name: str
    max_speed_kph: int
    report_interval_seconds: int
    protocol: Literal["gt06", "teltonika"]
    route: str
    stop_behavior: str
    coverage_behavior: str


PROFILES: Mapping[str, VehicleProfile] = {
    "trk": VehicleProfile(
        "trk",
        "long-haul truck",
        90,
        30,
        "gt06",
        "Mombasa–Nairobi–Eldoret corridor",
        "long-haul stops",
        "rural coverage gaps",
    ),
    "lry": VehicleProfile(
        "lry",
        "delivery lorry",
        60,
        60,
        "gt06",
        "Nairobi urban loops",
        "frequent delivery stops",
        "urban-canyon drift and coverage variation",
    ),
    "car": VehicleProfile(
        "car",
        "ride-hail and PSV car",
        70,
        20,
        "gt06",
        "dense Nairobi urban routes",
        "frequent passenger stops",
        "urban-canyon drift",
    ),
    "pik": VehicleProfile(
        "pik",
        "mixed pickup",
        80,
        45,
        "gt06",
        "mixed urban and regional routes",
        "mixed stop behavior",
        "mixed urban and rural coverage",
    ),
}

DEFAULT_PROFILE_MIX: Mapping[str, int] = {"trk": 40, "lry": 30, "car": 30}


def assign_profiles(vehicles: int, mix: Mapping[str, int] | None = None) -> tuple[str, ...]:
    """Allocate profile codes by largest remainder in stable profile order."""
    if not 1 <= vehicles <= 10_000:
        raise ValueError("vehicles must be between 1 and 10000")
    selected = DEFAULT_PROFILE_MIX if mix is None else mix
    if not selected or any(code not in PROFILES for code in selected):
        raise ValueError("profile mix contains no profiles or an unknown profile")
    if any(not isinstance(percent, int) or percent <= 0 for percent in selected.values()):
        raise ValueError("profile percentages must be positive integers")
    if sum(selected.values()) != 100:
        raise ValueError("profile percentages must sum to 100")

    order = tuple(code for code in PROFILES if code in selected)
    exact = {code: vehicles * selected[code] / 100 for code in order}
    counts = {code: int(exact[code]) for code in order}
    remaining = vehicles - sum(counts.values())
    remainder_order = sorted(
        order, key=lambda code: (-(exact[code] - counts[code]), order.index(code))
    )
    for code in remainder_order[:remaining]:
        counts[code] += 1
    return tuple(code for code in order for _ in range(counts[code]))
