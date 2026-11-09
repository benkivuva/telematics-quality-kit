"""Pure helpers shared by quality checks."""

from telematics.models.quality import CheckResult, Verdict

SCORES = {Verdict.PASS: 1.0, Verdict.WARN: 0.79, Verdict.BLOCK: 0.39}


def result(name: str, verdict: Verdict, **metric: float | str) -> CheckResult:
    """Build a check result using the canonical verdict score mapping."""
    return CheckResult(name=name, verdict=verdict, score=SCORES[verdict], metric=metric)


def fraction_verdict(fraction: float, warn: float, block: float) -> Verdict:
    """Map a flagged fraction to heuristic severity thresholds."""
    if fraction >= block:
        return Verdict.BLOCK
    if fraction >= warn:
        return Verdict.WARN
    return Verdict.PASS
