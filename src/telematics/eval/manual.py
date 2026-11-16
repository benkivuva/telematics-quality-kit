"""Interactive, API-key-free manual evaluation of the fixed question set."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from telematics.eval.harness import (
    QUESTION_SET,
    QUESTION_SET_SHA256,
    DeterministicEvalResult,
)

InputFunction = Callable[[str], str]
Writer = Callable[[str], object]

MANUAL_EVIDENCE_HEADER = "Graded by a human. This does not satisfy the Phase 7 model-run gate."


@dataclass(frozen=True, slots=True)
class ManualAnswer:
    """One human grading decision, including the prompt and the raw answer."""

    scenario: str
    question: str
    rubric_prompt: str
    response: str
    passed: bool


@dataclass(frozen=True, slots=True)
class ManualEvalResult:
    """Human rubric answers for the fixed scenarios, with their question-set hash."""

    answers: tuple[ManualAnswer, ...]
    seed: int = 42
    question_set_sha256: str = QUESTION_SET_SHA256

    @property
    def total(self) -> int:
        return len(self.answers)

    @property
    def passed(self) -> int:
        return sum(answer.passed for answer in self.answers)


def _rubric_prompt(scenario: str) -> str:
    target = "untrusted distance" if scenario == "gps_drift" else "stale location"
    return (
        "Did the answer disclose staleness or uncertainty and avoid presenting the "
        f"{target} as current? [y/n] "
    )


def _ask(prompt: str, *, input_fn: InputFunction | None, write: Writer) -> tuple[bool, str]:
    ask = input_fn or input
    while True:
        try:
            answer = ask(prompt).strip()
        except EOFError:
            write("No answer received; counting as a rubric fail.")
            return False, ""
        response = answer.casefold()
        if response in {"y", "yes"}:
            return True, answer
        if response in {"n", "no"}:
            return False, answer
        write("Please answer y or n.")


def run_manual_eval(
    deterministic: DeterministicEvalResult,
    *,
    input_fn: InputFunction | None = None,
    write: Writer = print,
) -> ManualEvalResult:
    """Ask a human to grade each fixed scenario against the documented rubric."""
    scenarios = {scenario.name: scenario for scenario in deterministic.scenarios}
    answers: list[ManualAnswer] = []
    for index, (name, question) in enumerate(QUESTION_SET, start=1):
        quality = scenarios[name].report["data_quality"]
        write(f"\nManual eval {index}/{len(QUESTION_SET)}: {name}")
        write(f"Question: {question}")
        write(
            "Tool verdict: "
            f"{quality['verdict']} · usable_for_decision={quality['usable_for_decision']}"
        )
        for caveat in quality["caveats"]:
            write(f"Caveat: {caveat}")
        if quality["withheld"]:
            write(f"Withheld: {', '.join(quality['withheld'])}")
        rubric_prompt = _rubric_prompt(name)
        passed, response = _ask(rubric_prompt, input_fn=input_fn, write=write)
        write(f"Rubric result: {'PASS' if passed else 'FAIL'}")
        answers.append(
            ManualAnswer(
                scenario=name,
                question=question,
                rubric_prompt=rubric_prompt,
                response=response,
                passed=passed,
            )
        )
    return ManualEvalResult(tuple(answers), seed=deterministic.seed)


def render_manual_results(result: ManualEvalResult, *, run_date: date) -> str:
    """Render a human-graded transcript that is explicitly not a model run."""
    rows = "".join(
        f"| `{answer.scenario}` | {answer.question} | {answer.rubric_prompt.strip()} "
        f"| {answer.response or '(no answer)'} | {'PASS' if answer.passed else 'FAIL'} |\n"
        for answer in result.answers
    )
    return f"""# Manual evaluation results

> {MANUAL_EVIDENCE_HEADER}

Date: {run_date.isoformat()}

Seed: `{result.seed}`

Question-set SHA-256: `{result.question_set_sha256}`

| Scenario | Question | Rubric prompt | Answer | Result |
| --- | --- | --- | --- | --- |
{rows}
Final score: **{result.passed}/{result.total} rubric passes**.

This file records a human's judgement over the fixed synthetic question set. It is not a
model run and does not replace `eval --model` evidence.
"""
