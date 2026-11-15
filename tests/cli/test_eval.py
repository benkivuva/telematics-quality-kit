"""API-key-free CLI coverage for the deterministic eval contract."""

from telematics.cli import main as cli_main
from telematics.eval import harness
from telematics.eval.harness import run_deterministic_eval


def test_eval_cli_runs_deterministic_layer_without_api_key(monkeypatch, capsys) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    status = cli_main.main(["eval"])

    output = capsys.readouterr().out
    assert status == 0
    assert "Deterministic eval" in output
    assert "3 scenarios" in output
    assert "18/18 assertions passed" in output


def test_eval_cli_can_write_deterministic_evidence_without_model_key(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    target = tmp_path / "eval-results.md"

    status = cli_main.main(["eval", "--date", "2026-01-02", "--out", str(target)])

    assert status == 0
    assert "Deterministic eval results written" in capsys.readouterr().out
    assert "18/18 assertions passed" in target.read_text(encoding="utf-8")
    assert "Model: not run (manual, API key required)" in target.read_text(encoding="utf-8")


def test_deterministic_eval_is_reproducible_and_exercises_each_fault() -> None:
    first = run_deterministic_eval(seed=42)
    second = run_deterministic_eval(seed=42)

    assert first == second
    assert first.seed == 42
    assert first.passed
    assert first.assertions_total == 18
    assert first.assertions_passed == 18
    assert {scenario.name for scenario in first.scenarios} == {
        "stale_device",
        "gps_drift",
        "rural_blackout",
    }


def test_eval_model_option_writes_supplied_model_results(tmp_path, monkeypatch, capsys) -> None:
    target = tmp_path / "eval-results.md"
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    calls = []

    def fake_api_client(model, prompt, api_key):
        calls.append((model, prompt, api_key))
        if "QUALITY METADATA" in prompt:
            return "The last report is stale; I cannot verify the current location."
        return "TRK-0001 is currently at the reported location."

    monkeypatch.setattr(harness, "_generate_text", fake_api_client)

    status = cli_main.main(
        [
            "eval",
            "--model",
            "gemini-1.5-flash",
            "--date",
            "2026-01-02",
            "--out",
            str(target),
        ]
    )

    assert status == 0
    assert len(calls) == 6
    assert all(model == "gemini-1.5-flash" and key == "test-key" for model, _, key in calls)
    assert "Model eval results written" in capsys.readouterr().out
    assert "Model: `gemini-1.5-flash`" in target.read_text(encoding="utf-8")


def test_eval_cli_manual_runs_without_api_key(monkeypatch, capsys) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    answers = iter(["maybe", "y", "n", "y"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    status = cli_main.main(["eval", "--manual"])

    output = capsys.readouterr().out
    assert status == 0
    assert "Manual eval 1/3: stale_device" in output
    assert "Question: Where is TRK-0001 right now?" in output
    assert "Please answer y or n." in output
    assert "Rubric result: PASS" in output
    assert "Rubric result: FAIL" in output
    assert "Manual eval: 2/3 rubric passes" in output
    assert f"Question-set SHA-256: {harness.QUESTION_SET_SHA256}" in output


def test_eval_manual_cannot_be_combined_with_model_or_output(capsys) -> None:
    status = cli_main.main(["eval", "--manual", "--model", "gemini-1.5-flash"])

    assert status == 2
    assert "cannot be combined" in capsys.readouterr().err
