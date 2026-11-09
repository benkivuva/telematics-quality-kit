"""Typed results produced by quality checks."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class Verdict(StrEnum):
    """Machine-readable quality status."""

    PASS = "PASS"
    WARN = "WARN"
    BLOCK = "BLOCK"


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One quality check result with its score and measured values."""

    name: str
    verdict: Verdict
    score: float
    metric: Mapping[str, int | float | str]
