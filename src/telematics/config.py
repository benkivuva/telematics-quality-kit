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
