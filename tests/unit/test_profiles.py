"""Synthetic Kenya fleet profile defaults and deterministic mix allocation."""

import pytest

from telematics.simulator.profiles import PROFILES, assign_profiles


@pytest.mark.unit
def test_profile_defaults_match_the_approved_heuristics() -> None:
    assert {
        code: (profile.max_speed_kph, profile.report_interval_seconds, profile.protocol)
        for code, profile in PROFILES.items()
    } == {
        "trk": (90, 30, "gt06"),
        "lry": (60, 60, "gt06"),
        "car": (70, 20, "gt06"),
        "pik": (80, 45, "gt06"),
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    ("vehicles", "expected"),
    [
        (1, {"trk": 1}),
        (12, {"trk": 5, "lry": 4, "car": 3}),
        (5000, {"trk": 2000, "lry": 1500, "car": 1500}),
    ],
)
def test_default_profile_mix_is_deterministic_and_has_requested_size(
    vehicles: int,
    expected: dict[str, int],
) -> None:
    assigned = assign_profiles(vehicles)
    counts = {code: assigned.count(code) for code in PROFILES}

    assert len(assigned) == vehicles
    assert {key: value for key, value in counts.items() if value} == expected


@pytest.mark.unit
def test_profile_mix_accepts_pickups_and_rejects_invalid_percentages() -> None:
    assert assign_profiles(8, {"trk": 25, "lry": 25, "car": 25, "pik": 25}) == (
        "trk",
        "trk",
        "lry",
        "lry",
        "car",
        "car",
        "pik",
        "pik",
    )

    with pytest.raises(ValueError):
        assign_profiles(4, {"trk": 80, "pik": 10})
