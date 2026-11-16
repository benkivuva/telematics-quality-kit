"""Executable command examples shown in the public README."""

from pathlib import Path

import pytest

README = Path(__file__).parents[2] / "README.md"


@pytest.mark.unit
def test_readme_shell_script_uses_the_nested_quality_field_path() -> None:
    text = README.read_text(encoding="utf-8")

    assert "expect field TRK-0001 data_quality.usable_for_decision false" in text


@pytest.mark.unit
def test_readme_documents_worse_than_and_manual_eval() -> None:
    text = README.read_text(encoding="utf-8")

    assert "`ls [--worse-than PASS\\|WARN\\|BLOCK] [--limit N]`" in text
    assert "uv run telematics eval --manual" in text


@pytest.mark.unit
def test_readme_distinguishes_clear_from_reset() -> None:
    text = README.read_text(encoding="utf-8")

    assert "Historical points that already recorded a fault stay" in text
    assert "wipe the simulator history" in text


@pytest.mark.unit
def test_readme_documents_the_coverage_and_e2e_commands() -> None:
    text = README.read_text(encoding="utf-8")

    assert "make coverage" in text
    assert "./e2e_test.sh" in text
