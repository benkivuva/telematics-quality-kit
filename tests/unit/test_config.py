"""Heuristic defaults and validation for freshness configuration."""

import pytest

from telematics.config import FreshnessConfig


@pytest.mark.unit
def test_freshness_config_defaults_match_documented_heuristics() -> None:
    config = FreshnessConfig()

    assert config.expected_interval_seconds == 30
    assert config.warn_after_intervals == 2
    assert config.block_after_intervals == 10


@pytest.mark.unit
def test_freshness_config_requires_positive_ordered_thresholds() -> None:
    with pytest.raises(ValueError):
        FreshnessConfig(expected_interval_seconds=0)
    with pytest.raises(ValueError):
        FreshnessConfig(warn_after_intervals=10, block_after_intervals=2)
