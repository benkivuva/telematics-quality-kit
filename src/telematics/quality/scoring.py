# Phase 2 partial-scoring policy: freshness is the only implemented check,
# so it carries 100% of the score. Do not normalize against the six-check v0.1
# weights until the other checks are implemented.
"""Scoring weights for implemented Phase 2 quality checks."""

from collections.abc import Mapping
from types import MappingProxyType

from telematics.models.quality import CheckResult, Verdict

PHASE_2_WEIGHTS: Mapping[str, float] = MappingProxyType({"freshness": 1.0})

_VERDICT_CAPS: Mapping[Verdict, float] = MappingProxyType(
    {Verdict.PASS: 1.0, Verdict.WARN: 0.79, Verdict.BLOCK: 0.39}
)


def score_checks(results: tuple[CheckResult, ...]) -> float:
    """Compute the Phase 2 weighted score, capped by the worst verdict."""
    if not results:
        raise ValueError("at least one quality result is required")
    weighted = [(result, PHASE_2_WEIGHTS.get(result.name, 0.0)) for result in results]
    included = [(result, weight) for result, weight in weighted if weight > 0]
    if not included:
        raise ValueError("no implemented quality checks were provided")
    total_weight = sum(weight for _, weight in included)
    mean = sum(result.score * weight for result, weight in included) / total_weight
    cap = min(_VERDICT_CAPS[result.verdict] for result, _ in included)
    return min(mean, cap)
