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

__all__ = [
    "QUESTION_SET_SHA256",
    "DeterministicEvalResult",
    "ModelEvalResult",
    "grade_answer",
    "render_deterministic_results",
    "render_eval_results",
    "run_deterministic_eval",
    "run_model_eval",
]
