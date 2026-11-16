"""Deterministic and optional model-based evaluation harnesses."""

from telematics.eval.harness import (
    QUESTION_SET_SHA256,
    DeterministicEvalResult,
    ModelEvalResult,
    grade_answer,
    render_deterministic_results,
    render_eval_results,
    run_deterministic_eval,
    run_model_eval,
)
from telematics.eval.manual import (
    MANUAL_EVIDENCE_HEADER,
    ManualAnswer,
    ManualEvalResult,
    render_manual_results,
    run_manual_eval,
)

__all__ = [
    "MANUAL_EVIDENCE_HEADER",
    "QUESTION_SET_SHA256",
    "DeterministicEvalResult",
    "ManualAnswer",
    "ManualEvalResult",
    "ModelEvalResult",
    "grade_answer",
    "render_deterministic_results",
    "render_eval_results",
    "render_manual_results",
    "run_deterministic_eval",
    "run_manual_eval",
    "run_model_eval",
]
