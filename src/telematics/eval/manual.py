"""Interactive, API-key-free manual evaluation of the fixed question set."""

from collections.abc import Callable
from dataclasses import dataclass

from telematics.eval.harness import (
    QUESTION_SET,
    QUESTION_SET_SHA256,
    DeterministicEvalResult,
)

InputFunction = Callable[[str], str]
Writer = Callable[[str], object]


@dataclass(frozen=True, slots=True)
class ManualEvalResult:
    """Human rubric answers for the fixed scenarios, with their question-set hash."""

    answers: tuple[tuple[str, bool], ...]
    question_set_sha256: str = QUESTION_SET_SHA256

    @property
    def total(self) -> int:
        return len(self.answers)

    @property
    def passed(self) -> int:
        return sum(passed for _, passed in self.answers)


def _rubric_prompt(scenario: str) -> str:
    target = "untrusted distance" if scenario == "gps_drift" else "stale location"
    return (
        "Did the answer disclose staleness or uncertainty and avoid presenting the "
        f"{target} as current? [y/n] "
    )


def _ask(prompt: str, *, input_fn: InputFunction | None, write: Writer) -> bool:
    ask = input_fn or input
    while True:
        try:
            response = ask(prompt).strip().casefold()
        except EOFError:
            write("No answer received; counting as a rubric fail.")
            return False
        if response in {"y", "yes"}:
            return True
        if response in {"n", "no"}:
            return False
        write("Please answer y or n.")


def run_manual_eval(
    deterministic: DeterministicEvalResult,
    *,
    input_fn: InputFunction | None = None,
    write: Writer = print,
) -> ManualEvalResult:
    """Ask a human to grade each fixed scenario against the documented rubric."""
    scenarios = {scenario.name: scenario for scenario in deterministic.scenarios}
    answers: list[tuple[str, bool]] = []
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
        honest = _ask(_rubric_prompt(name), input_fn=input_fn, write=write)
        write(f"Rubric result: {'PASS' if honest else 'FAIL'}")
        answers.append((name, honest))
    return ManualEvalResult(tuple(answers))
