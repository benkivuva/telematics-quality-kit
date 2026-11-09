"""Tests for the complete v0.1 six-check scoring policy."""

import pytest

from telematics.models.quality import CheckResult, Verdict
from telematics.quality.scoring import V0_1_WEIGHTS, score_checks


@pytest.mark.unit
def test_v0_1_weights_cover_all_six_checks_and_sum_to_one() -> None:
    assert dict(V0_1_WEIGHTS) == {
        "freshness": 0.30,
        "drift": 0.25,
        "duplicates": 0.15,
        "ignition": 0.10,
        "plausibility": 0.15,
        "fuel": 0.05,
    }
    assert sum(V0_1_WEIGHTS.values()) == 1.0


@pytest.mark.unit
@pytest.mark.parametrize(
    ("verdict", "check_score", "expected_score"),
    [
        (Verdict.PASS, 1.0, 1.0),
        (Verdict.WARN, 0.79, 0.79),
        (Verdict.BLOCK, 0.39, 0.39),
    ],
)
def test_single_check_scoring_uses_the_verdict_cap(
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


@pytest.mark.unit
def test_full_weighted_score_is_capped_by_worst_verdict() -> None:
    results = tuple(
        CheckResult(name=name, verdict=verdict, score=score, metric={})
        for name, verdict, score in (
            ("freshness", Verdict.PASS, 1.0),
            ("drift", Verdict.PASS, 1.0),
            ("duplicates", Verdict.PASS, 1.0),
            ("ignition", Verdict.PASS, 1.0),
            ("plausibility", Verdict.PASS, 1.0),
            ("fuel", Verdict.BLOCK, 0.39),
        )
    )

    assert score_checks(results) == 0.39
