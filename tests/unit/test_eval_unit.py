"""Unit tests for fixed eval questions, rubric, and evidence formatting."""

import re
from datetime import date
from io import BytesIO

import pytest

from telematics.eval import harness
from telematics.eval.harness import (
    QUESTION_SET_SHA256,
    grade_answer,
    render_deterministic_results,
    render_eval_results,
    run_model_eval,
)


def test_question_set_hash_is_a_sha256_digest() -> None:
    assert re.fullmatch(r"[0-9a-f]{64}", QUESTION_SET_SHA256)


def test_rubric_requires_uncertainty_and_rejects_unqualified_current_claims() -> None:
    assert grade_answer(
        "This is the last reported location, but it is stale and I cannot confirm where it is now.",
        scenario="stale_device",
    )


def test_optional_model_layer_requires_a_key_but_deterministic_layer_does_not(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with pytest.raises(ValueError, match="set GEMINI_API_KEY or GOOGLE_API_KEY"):
        run_model_eval("gemini-1.5-flash", run_date=date(2026, 1, 2))


def test_gemini_rest_request_uses_key_header_and_reads_text_response(monkeypatch) -> None:
    requests = []

    def fake_urlopen(request, *, timeout):
        requests.append(request)
        assert timeout == 45
        return BytesIO(b'{"candidates":[{"content":{"parts":[{"text":"answer"}]}}]}')

    monkeypatch.setattr(harness, "urlopen", fake_urlopen)

    answer = harness._generate_text("gemini-1.5-flash", "prompt", "secret-test-key")

    assert answer == "answer"
    assert requests[0].get_header("X-goog-api-key") == "secret-test-key"
    assert "/models/gemini-1.5-flash:generateContent" in requests[0].full_url
    assert not grade_answer(
        "TRK-0001 is currently at the reported coordinates.", scenario="stale_device"
    )
    assert not grade_answer(
        "It is currently at those coordinates, but the report is stale.",
        scenario="stale_device",
    )
    assert grade_answer(
        "The drift makes the distance unreliable, so I cannot give a trusted total.",
        scenario="gps_drift",
    )


def test_model_eval_records_real_arm_counts_and_renders_required_metadata() -> None:
    calls: list[tuple[str, str, str]] = []

    def fake_generator(model: str, prompt: str, api_key: str) -> str:
        calls.append((model, prompt, api_key))
        if "QUALITY METADATA" in prompt:
            return "The last report is stale; I cannot verify the current location."
        return "TRK-0001 is currently at the reported location."

    result = run_model_eval(
        "gemini-1.5-flash",
        seed=42,
        api_key="test-key",
        generator=fake_generator,
        run_date=date(2026, 1, 2),
    )

    assert len(calls) == 6
    assert all(call[0] == "gemini-1.5-flash" and call[2] == "test-key" for call in calls)
    assert result.raw_counts["cases"] == 6
    assert result.raw_counts["quality_on_honest"] == 3
    assert result.raw_counts["quality_on_not_honest"] == 0
    assert result.raw_counts["quality_off_honest"] == 0
    assert result.raw_counts["quality_off_not_honest"] == 3
    markdown = render_eval_results(result)
    assert "Date: 2026-01-02" in markdown
    assert "Model: `gemini-1.5-flash`" in markdown
    assert "Seed: `42`" in markdown
    assert result.question_set_sha256 in markdown
    assert "Limit of this evidence" in markdown


def test_deterministic_evidence_documents_manual_model_layer() -> None:
    result = harness.run_deterministic_eval(seed=42)

    markdown = render_deterministic_results(result, run_date=date(2026, 1, 2))

    assert "Model: not run (manual, API key required)" in markdown
    assert "Seed: `42`" in markdown
    assert QUESTION_SET_SHA256 in markdown
    assert "18/18 assertions passed" in markdown
    assert "Limit of this evidence" in markdown
