"""v0.1 six-check score weights and verdict caps."""

from collections.abc import Mapping
from types import MappingProxyType

from telematics.models.quality import CheckResult, Verdict

V0_1_WEIGHTS: Mapping[str, float] = MappingProxyType(
    {
        "freshness": 0.30,
        "drift": 0.25,
        "duplicates": 0.15,
        "ignition": 0.10,
        "plausibility": 0.15,
        "fuel": 0.05,
    }
)

_VERDICT_CAPS: Mapping[Verdict, float] = MappingProxyType(
    {Verdict.PASS: 1.0, Verdict.WARN: 0.79, Verdict.BLOCK: 0.39}
)


def score_checks(results: tuple[CheckResult, ...]) -> float:
    """Return the normalized v0.1 weighted score capped by the worst verdict.

    A subset is accepted while callers assemble checks incrementally; its score
    is normalized over the supplied checks. Unknown or repeated names are bugs.
    """
    if not results:
        raise ValueError("at least one quality result is required")
    names = [result.name for result in results]
    if len(names) != len(set(names)):
        raise ValueError("quality result names must be unique")
    unknown = set(names).difference(V0_1_WEIGHTS)
    if unknown:
        raise ValueError(f"unknown quality checks: {', '.join(sorted(unknown))}")
    invalid_scores = [result.name for result in results if not 0 <= result.score <= 1]
    if invalid_scores:
        raise ValueError("quality check scores must be in [0, 1]")
    total_weight = sum(V0_1_WEIGHTS[result.name] for result in results)
    mean = sum(result.score * V0_1_WEIGHTS[result.name] for result in results) / total_weight
    cap = min(_VERDICT_CAPS[result.verdict] for result in results)
    return min(mean, cap)
