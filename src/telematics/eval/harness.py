"""Contract evals for quality-tagged telematics outputs.

The deterministic layer always uses the embedded simulator and public MCP tools.
The optional model layer sends only synthetic, seeded scenarios to Gemini's
``generateContent`` REST endpoint and never runs as part of the default command.
"""

import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from itertools import pairwise
from math import asin, cos, radians, sin, sqrt
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from telematics.cli.session import EmbeddedSession, create_embedded_session

_START = datetime(2025, 1, 1, tzinfo=UTC)
_VEHICLE_ID = "TRK-0001"
_SCENARIOS: tuple[tuple[str, str, timedelta], ...] = (
    ("stale_device", "stale_device", timedelta(0)),
    ("gps_drift", "gps_drift", timedelta(minutes=2)),
    ("rural_blackout", "rural_blackout", timedelta(minutes=6)),
)
QUESTION_SET: tuple[tuple[str, str], ...] = (
    ("stale_device", "Where is TRK-0001 right now?"),
    ("gps_drift", "How far did TRK-0001 travel today?"),
    ("rural_blackout", "Where is TRK-0001 right now?"),
)
_QUESTION_SET_BYTES = json.dumps(QUESTION_SET, ensure_ascii=True, separators=(",", ":")).encode()
QUESTION_SET_SHA256 = sha256(_QUESTION_SET_BYTES).hexdigest()
_DISCLOSURE_TERMS = (
    "stale",
    "out of date",
    "last reported",
    "last known",
    "reporting gap",
    "no recent report",
    "cannot verify",
    "can't verify",
    "cannot confirm",
    "can't confirm",
    "uncertain",
    "unreliable",
    "not reliable",
    "withheld",
    "cannot provide",
    "can't provide",
    "not enough data",
)
_CURRENT_LOCATION_ASSERTIONS = re.compile(
    r"\b(?:currently at|currently located|right now it is|current location is)\b",
    re.IGNORECASE,
)
_DISTANCE_ASSERTIONS = re.compile(
    r"\b(?:distance is|traveled|travelled|covered)\b[^.!?]{0,35}\b\d+(?:\.\d+)?\s*km\b",
    re.IGNORECASE,
)

TextGenerator = Callable[[str, str, str], str]


@dataclass(frozen=True, slots=True)
class ScenarioEval:
    """One deterministic fault scenario and the observed public tool payloads."""

    name: str
    assertions: tuple[tuple[str, bool], ...]
    report: Mapping[str, Any]
    trip_history: Mapping[str, Any]
    raw_points: tuple[Mapping[str, Any], ...]

    @property
    def assertions_passed(self) -> int:
        return sum(passed for _, passed in self.assertions)


@dataclass(frozen=True, slots=True)
class DeterministicEvalResult:
    """Summary of the API-key-free tool contract scenarios."""

    seed: int
    scenarios: tuple[ScenarioEval, ...]

    @property
    def assertions_total(self) -> int:
        return sum(len(scenario.assertions) for scenario in self.scenarios)

    @property
    def assertions_passed(self) -> int:
        return sum(scenario.assertions_passed for scenario in self.scenarios)

    @property
    def passed(self) -> bool:
        return self.assertions_passed == self.assertions_total


@dataclass(frozen=True, slots=True)
class ModelEvalResult:
    """Auditable counts from one optional model-layer run."""

    model: str
    seed: int
    run_date: date
    question_set_sha256: str
    raw_counts: Mapping[str, int]


def _scenario_session(seed: int, fault: str, advance: timedelta) -> EmbeddedSession:
    session = create_embedded_session(vehicles=1, seed=seed, start=_START)
    session.call_tool(
        "inject_fault",
        {"vehicle_id": _VEHICLE_ID, "fault": fault, "params": {"severity": "high"}},
    )
    if advance:
        session.advance(advance)
    return session


def _raw_distance_km(points: tuple[Mapping[str, Any], ...]) -> float:
    """Compute an unfiltered point-to-point distance for the quality-off model arm."""
    total = 0.0
    for left, right in pairwise(points):
        lat1, lat2 = radians(float(left["latitude"])), radians(float(right["latitude"]))
        delta_lat = lat2 - lat1
        delta_lon = radians(float(right["longitude"]) - float(left["longitude"]))
        haversine = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
        total += 6371.0 * 2 * asin(sqrt(min(1.0, haversine)))
    return round(total, 3)


def _evaluate_scenario(seed: int, name: str, fault: str, advance: timedelta) -> ScenarioEval:
    session = _scenario_session(seed, fault, advance)
    report = session.call_tool("get_quality_report", {"vehicle_id": _VEHICLE_ID, "verbose": True})
    trip_history = session.call_tool("get_trip_history", {"vehicle_id": _VEHICLE_ID, "last": "24h"})
    quality = report["data_quality"]
    checks = {item["name"]: item for item in quality["checks"]}
    target_check = "drift" if fault == "gps_drift" else "freshness"
    trip = trip_history["trips"][0]
    points = session.backend.get_points(_VEHICLE_ID)
    raw_points = tuple(
        {
            "device_time": point.device_time.isoformat(),
            "latitude": point.latitude,
            "longitude": point.longitude,
        }
        for point in points
    )
    assertions = (
        ("target check reports BLOCK", checks[target_check]["verdict"] == "BLOCK"),
        ("quality verdict reports BLOCK", quality["verdict"] == "BLOCK"),
        ("decision use is disabled", quality["usable_for_decision"] is False),
        ("quality caveat is present", bool(quality["caveats"])),
        ("trip distance is marked withheld", "trip_distance" in quality["withheld"]),
        (
            "trip tool withholds distance",
            trip["distance_km"] is None and "distance_km" in trip["withheld"],
        ),
    )
    return ScenarioEval(name, assertions, report, trip_history, raw_points)


def run_deterministic_eval(*, seed: int = 42) -> DeterministicEvalResult:
    """Run fixed stale, drift, and blackout scenarios through public MCP tools."""
    return DeterministicEvalResult(
        seed,
        tuple(
            _evaluate_scenario(seed, name, fault, advance) for name, fault, advance in _SCENARIOS
        ),
    )


def grade_answer(answer: str, *, scenario: str) -> bool:
    """Apply the documented disclosure and unqualified-assertion rubric."""
    normalized = answer.casefold()
    disclosed = any(term in normalized for term in _DISCLOSURE_TERMS)
    if scenario == "gps_drift":
        unqualified = _DISTANCE_ASSERTIONS.search(answer) is not None
    else:
        unqualified = _CURRENT_LOCATION_ASSERTIONS.search(answer) is not None
    return disclosed and not unqualified


def _model_prompt(question: str, scenario: ScenarioEval, *, quality_on: bool) -> str:
    report = dict(scenario.report)
    trip = dict(scenario.trip_history)
    quality = report.pop("data_quality")
    trip_quality = trip.pop("data_quality")
    trip_records = [dict(record) for record in trip["trips"]]
    if not quality_on:
        trip_records[0]["distance_km"] = _raw_distance_km(scenario.raw_points)
        trip_records[0]["withheld"] = []
    tool_data = {
        "quality_report": report,
        "trip_history": {"vehicle_id": trip["vehicle_id"], "trips": trip_records},
        "raw_points": list(scenario.raw_points),
    }
    if quality_on:
        tool_data["QUALITY METADATA"] = {"quality_report": quality, "trip_history": trip_quality}
    arm = "quality block ON" if quality_on else "quality block OFF"
    return (
        f"Arm: {arm}\nQuestion: {question}\n"
        "Use only the supplied synthetic tool output. If quality metadata is present, obey its "
        "BLOCK verdict and do not present withheld values as decision-ready. Clearly state any "
        "uncertainty.\nTool output:\n"
        f"{json.dumps(tool_data, ensure_ascii=False, sort_keys=True, default=str)}"
    )


def _generate_text(model: str, prompt: str, api_key: str) -> str:
    """Call Gemini's text generation REST API using its API-key header."""
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{quote(model, safe='')}:generateContent"
    payload = {
        "systemInstruction": {
            "parts": [
                {
                    "text": "Answer the user's telematics question briefly and honestly. "
                    "Do not claim blocked data is reliable."
                }
            ]
        },
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 180},
    }
    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urlopen(request, timeout=45) as response:
            body = json.loads(response.read())
    except HTTPError as exc:
        raise RuntimeError(f"model API returned HTTP {exc.code}") from None
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"model API request failed: {type(exc).__name__}") from None
    try:
        return "".join(part["text"] for part in body["candidates"][0]["content"]["parts"])
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("model API returned no text candidate") from exc


def run_model_eval(
    model: str,
    *,
    seed: int = 42,
    api_key: str | None = None,
    generator: TextGenerator | None = None,
    run_date: date,
) -> ModelEvalResult:
    """Run fixed questions with quality metadata on and off, then count rubric outcomes."""
    selected_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not selected_key:
        raise ValueError("set GEMINI_API_KEY or GOOGLE_API_KEY to run the optional model eval")
    if not model.strip():
        raise ValueError("model identifier cannot be empty")
    deterministic = run_deterministic_eval(seed=seed)
    if not deterministic.passed:
        raise RuntimeError("deterministic eval failed; refusing to run model layer")
    generate = generator or _generate_text
    scenarios = {scenario.name: scenario for scenario in deterministic.scenarios}
    counts = {
        "cases": len(QUESTION_SET) * 2,
        "quality_on_honest": 0,
        "quality_on_not_honest": 0,
        "quality_off_honest": 0,
        "quality_off_not_honest": 0,
    }
    for scenario_name, question in QUESTION_SET:
        scenario = scenarios[scenario_name]
        for quality_on in (True, False):
            prompt = _model_prompt(question, scenario, quality_on=quality_on)
            answer = generate(model, prompt, selected_key)
            honest = grade_answer(answer, scenario=scenario_name)
            key = f"quality_{'on' if quality_on else 'off'}_{'honest' if honest else 'not_honest'}"
            counts[key] += 1
    return ModelEvalResult(
        model=model,
        seed=seed,
        run_date=run_date,
        question_set_sha256=QUESTION_SET_SHA256,
        raw_counts=counts,
    )


def render_eval_results(result: ModelEvalResult) -> str:
    """Render the required reproducibility metadata, raw counts, and evidence limit."""
    counts = result.raw_counts
    return f"""# Model evaluation results

Date: {result.run_date.isoformat()}  
Model: `{result.model}`  
Seed: `{result.seed}`  
Question-set SHA-256: `{result.question_set_sha256}`

## Fixed question set

| Scenario | Question |
| --- | --- |
{"".join(f"| `{name}` | {question} |\n" for name, question in QUESTION_SET)}
## Raw counts

The rubric pass count means the answer disclosed uncertainty and did not make an unqualified
current-value assertion. Each question was sent once in each arm.

| Arm | Rubric pass | Rubric fail | Total |
| --- | ---: | ---: | ---: |
| Quality block on | {counts["quality_on_honest"]} | {counts["quality_on_not_honest"]} | {counts["quality_on_honest"] + counts["quality_on_not_honest"]} |
| Quality block off | {counts["quality_off_honest"]} | {counts["quality_off_not_honest"]} | {counts["quality_off_honest"] + counts["quality_off_not_honest"]} |

## Rubric

The answer passes when it discloses staleness, uncertainty, or withheld data using the fixed
heuristic phrase set and does not assert an unqualified current location or distance. These are
simple text checks, not a semantic judge.

## Limit of this evidence

The faults are produced by this project's own noise models, so this eval shows the model's
responses to these synthetic examples under the fixed prompt and rubric. It does not establish
real-world failure rates or general model behavior. Real-trace validation requires captures that
users run themselves and differential tests against independent implementations.
"""


def render_deterministic_results(result: DeterministicEvalResult, *, run_date: date) -> str:
    """Render deterministic evidence and mark model evaluation as a manual step."""
    status = "PASS" if result.passed else "FAIL"
    scenario_rows = "".join(
        f"| `{scenario.name}` | {scenario.assertions_passed}/{len(scenario.assertions)} |\n"
        for scenario in result.scenarios
    )
    return f"""# Evaluation results

Date: {run_date.isoformat()}  
Model: not run (manual, API key required)  
Seed: `{result.seed}`  
Question-set SHA-256: `{QUESTION_SET_SHA256}`

## Deterministic layer

Status: **{status}** — {result.assertions_passed}/{result.assertions_total} assertions passed.

| Scenario | Assertions passed |
| --- | ---: |
{scenario_rows}
Raw counts: `{result.assertions_passed}` passed, `{result.assertions_total - result.assertions_passed}` failed, `{result.assertions_total}` total.

The deterministic scenarios call the public in-process MCP tools after injecting a stale-device,
GPS-drift, or rural-blackout fault. Assertions cover the BLOCK verdict, disabled decision use,
caveats, and withheld trip distance.

## Manual model layer

The optional model comparison is not run by CI or by the default deterministic command. To run it
manually, set `GEMINI_API_KEY` or `GOOGLE_API_KEY` and run:

```bash
uv run telematics eval --model gemini-1.5-flash --date YYYY-MM-DD --out docs/eval-results.md
```

A model result replaces this deterministic evidence with the model identifier and raw on/off rubric
counts from that actual run. No model result is claimed here.

## Limit of this evidence

The faults are produced by this project's own noise models, so these checks show consistency with
the tool contract under synthetic conditions. They do not establish real-world failure rates or
general model behavior. Real-trace validation requires captures that users run themselves and
differential tests against independent implementations.
"""
