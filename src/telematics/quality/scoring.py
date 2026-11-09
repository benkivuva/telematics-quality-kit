# Phase 2 partial-scoring policy: freshness is the only implemented check,
# so it carries 100% of the score. Do not normalize against the six-check v0.1
# weights until the other checks are implemented.
"""Scoring weights for implemented Phase 2 quality checks."""

from collections.abc import Mapping
from types import MappingProxyType

PHASE_2_WEIGHTS: Mapping[str, float] = MappingProxyType({"freshness": 1.0})
