"""Phase 2 partial-scoring policy tests."""

import pytest

from telematics.quality.scoring import PHASE_2_WEIGHTS


@pytest.mark.unit
def test_phase_two_freshness_weight_is_the_entire_score() -> None:
    assert dict(PHASE_2_WEIGHTS) == {"freshness": 1.0}
    assert sum(PHASE_2_WEIGHTS.values()) == 1.0
