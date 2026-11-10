"""Heuristic defaults and validation for freshness configuration."""

import pytest

from telematics.config import DriftConfig, FreshnessConfig, drift_config_from_environment


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


@pytest.mark.unit
def test_drift_config_can_be_overridden_by_documented_environment_variables() -> None:
    config = drift_config_from_environment(
        {
            "TELEMATICS_DRIFT_WARN_FRACTION": "0.02",
            "TELEMATICS_DRIFT_BLOCK_FRACTION": "0.08",
            "TELEMATICS_DRIFT_STATIONARY_JITTER_METERS": "40",
        }
    )

    assert config == DriftConfig(
        warn_fraction=0.02,
        block_fraction=0.08,
        stationary_jitter_meters=40,
    )


@pytest.mark.unit
def test_drift_config_rejects_invalid_environment_values() -> None:
    with pytest.raises(ValueError, match="TELEMATICS_DRIFT_WARN_FRACTION"):
        drift_config_from_environment({"TELEMATICS_DRIFT_WARN_FRACTION": "invalid"})
