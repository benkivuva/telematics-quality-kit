"""Phase 2 partial-scoring policy tests."""

import pytest

from telematics.models.quality import CheckResult, Verdict
from telematics.quality.scoring import PHASE_2_WEIGHTS, score_checks


@pytest.mark.unit
def test_phase_two_freshness_weight_is_the_entire_score() -> None:
    assert dict(PHASE_2_WEIGHTS) == {"freshness": 1.0}
    assert sum(PHASE_2_WEIGHTS.values()) == 1.0


@pytest.mark.unit
@pytest.mark.parametrize(
    ("verdict", "check_score", "expected_score"),
    [
        (Verdict.PASS, 1.0, 1.0),
        (Verdict.WARN, 0.79, 0.79),
        (Verdict.BLOCK, 0.39, 0.39),
    ],
)
def test_phase_two_scoring_uses_the_verdict_cap(
    verdict: Verdict,
    check_score: float,
    expected_score: float,
) -> None:
    result = CheckResult(
        name="freshness",
        verdict=verdict,
        score=check_score,
        metric={},
    )

    assert score_checks((result,)) == expected_score
