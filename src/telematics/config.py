"""Configurable heuristic defaults for quality evaluation."""

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
