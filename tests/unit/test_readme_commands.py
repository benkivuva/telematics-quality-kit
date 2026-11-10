"""Executable command examples shown in the public README."""

from pathlib import Path

import pytest

README = Path(__file__).parents[2] / "README.md"


@pytest.mark.unit
def test_readme_shell_script_uses_the_nested_quality_field_path() -> None:
    text = README.read_text(encoding="utf-8")

    assert "expect field TRK-0001 data_quality.usable_for_decision false" in text
