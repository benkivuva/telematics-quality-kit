"""Typed results produced by quality checks."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum


class Verdict(StrEnum):
    """Machine-readable quality status."""

    PASS = "PASS"
    WARN = "WARN"
    BLOCK = "BLOCK"

    @property
    def severity(self) -> int:
        """Return the ordered severity, so PASS < WARN < BLOCK is explicit."""
        return _SEVERITY[self]


_SEVERITY = {Verdict.PASS: 0, Verdict.WARN: 1, Verdict.BLOCK: 2}


def worst_verdict(verdicts: Iterable[Verdict]) -> Verdict:
    """Return the most severe verdict, defaulting to PASS for an empty input."""
    return max(verdicts, key=lambda verdict: verdict.severity, default=Verdict.PASS)


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One quality check result with its score and measured values."""

    name: str
    verdict: Verdict
    score: float
    metric: Mapping[str, int | float | str]
