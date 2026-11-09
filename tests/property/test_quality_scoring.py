"""Properties for weighted quality score behavior."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from telematics.models.quality import CheckResult, Verdict
from telematics.quality.scoring import V0_1_WEIGHTS, score_checks


@pytest.mark.property
@given(st.lists(st.floats(min_value=0, max_value=1, allow_nan=False), min_size=1, max_size=6))
def test_score_is_bounded_and_independent_of_check_order(scores: list[float]) -> None:
    names = tuple(V0_1_WEIGHTS)[: len(scores)]
    results = tuple(
        CheckResult(name, Verdict.PASS, score, {}) for name, score in zip(names, scores)
    )

    assert 0 <= score_checks(results) <= 1
    assert score_checks(results) == score_checks(tuple(reversed(results)))


@pytest.mark.property
@given(
    st.lists(
        st.sampled_from(tuple(V0_1_WEIGHTS)),
        min_size=1,
        max_size=6,
        unique=True,
    )
)
def test_any_block_verdict_caps_weighted_result(names: list[str]) -> None:
    results = tuple(
        CheckResult(name, Verdict.BLOCK if index == 0 else Verdict.PASS, 1.0, {})
        for index, name in enumerate(names)
    )

    assert score_checks(results) <= 0.39
