"""Configurable heuristic defaults for quality evaluation."""

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FreshnessConfig:
    """Freshness cadence and verdict thresholds, expressed as heuristics."""

    expected_interval_seconds: int = 30
    warn_after_intervals: int = 2
    block_after_intervals: int = 10

    def __post_init__(self) -> None:
        if self.expected_interval_seconds <= 0:
            raise ValueError("expected interval must be positive")
        if self.warn_after_intervals <= 0:
            raise ValueError("WARN threshold must be positive")
        if self.block_after_intervals <= self.warn_after_intervals:
            raise ValueError("BLOCK threshold must be greater than WARN threshold")


@dataclass(frozen=True, slots=True)
class DriftConfig:
    """Heuristic thresholds for implausible movement."""

    warn_fraction: float = 0.01
    block_fraction: float = 0.05
    stationary_jitter_meters: float = 25.0

    def __post_init__(self) -> None:
        values = (self.warn_fraction, self.block_fraction, self.stationary_jitter_meters)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("drift thresholds must be finite numbers")
        if self.warn_fraction <= 0 or self.block_fraction <= self.warn_fraction:
            raise ValueError("drift block fraction must be greater than a positive warn fraction")
        if self.stationary_jitter_meters <= 0:
            raise ValueError("stationary jitter threshold must be positive")


def drift_config_from_environment(
    environment: Mapping[str, str] | None = None,
) -> DriftConfig:
    """Build drift thresholds from documented TELEMATICS_* environment variables."""
    values = environment if environment is not None else os.environ
    defaults = DriftConfig()
    names = {
        "TELEMATICS_DRIFT_WARN_FRACTION": "warn_fraction",
        "TELEMATICS_DRIFT_BLOCK_FRACTION": "block_fraction",
        "TELEMATICS_DRIFT_STATIONARY_JITTER_METERS": "stationary_jitter_meters",
    }
    parsed: dict[str, float] = {}
    for variable, field in names.items():
        if variable not in values:
            continue
        try:
            parsed[field] = float(values[variable])
        except ValueError as exc:
            raise ValueError(f"{variable} must be a number") from exc
    try:
        return DriftConfig(
            warn_fraction=parsed.get("warn_fraction", defaults.warn_fraction),
            block_fraction=parsed.get("block_fraction", defaults.block_fraction),
            stationary_jitter_meters=parsed.get(
                "stationary_jitter_meters", defaults.stationary_jitter_meters
            ),
        )
    except ValueError as exc:
        raise ValueError(f"invalid drift threshold configuration: {exc}") from exc


@dataclass(frozen=True, slots=True)
class DuplicatesConfig:
    """Heuristic thresholds for repeats and excess heartbeat rates."""

    warn_fraction: float = 0.05
    block_fraction: float = 0.25
    heartbeat_rate_ratio: float = 3.0


@dataclass(frozen=True, slots=True)
class IgnitionConfig:
    """Heuristic ignition debounce and chatter window."""

    max_transitions: int = 4
    window_seconds: int = 120
    debounce_seconds: int = 2


@dataclass(frozen=True, slots=True)
class PlausibilityConfig:
    """Heuristic structural and clock plausibility limits."""

    warn_clock_skew_seconds: int = 300
    block_clock_skew_seconds: int = 3600


@dataclass(frozen=True, slots=True)
class FuelConfig:
    """Heuristic unexplained fuel drop thresholds."""

    unexplained_drop_percent: float = 10.0
    max_distance_km: float = 1.0
