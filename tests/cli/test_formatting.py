"""CLI formatting tests for text-first verdicts and JSON output."""

import json

import pytest

from telematics.cli.formatting import json_line, render_verdict, use_color
from telematics.models.quality import Verdict


@pytest.mark.unit
@pytest.mark.parametrize(
    ("verdict", "expected"),
    [
        (Verdict.PASS, "✓ PASS — trust it"),
        (Verdict.WARN, "⚠ WARN — be careful"),
        (Verdict.BLOCK, "⛔ BLOCK — don't trust it"),
    ],
)
def test_verdict_always_has_symbol_and_plain_language_label(
    verdict: Verdict, expected: str
) -> None:
    assert render_verdict(verdict) == expected


@pytest.mark.unit
def test_no_color_environment_disables_terminal_colors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")

    assert use_color(is_terminal=True) is False


@pytest.mark.unit
def test_non_terminal_output_is_not_colored() -> None:
    assert use_color(is_terminal=False) is False


@pytest.mark.unit
def test_json_line_serializes_pydantic_model_as_one_json_object() -> None:
    from telematics.mcp.schemas import ListVehiclesOutput

    line = json_line(ListVehiclesOutput(vehicles=[]))

    assert json.loads(line) == {"schema_version": "1.0", "vehicles": [], "next_cursor": None}
    assert "\n" not in line
