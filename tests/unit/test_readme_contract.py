"""README contract: licence and clean Markdown text."""

from pathlib import Path

import pytest

README = Path(__file__).parents[2] / "README.md"


@pytest.mark.unit
def test_readme_declares_apache_2_0_license() -> None:
    text = README.read_text(encoding="utf-8")

    assert "Apache-2.0" in text
    assert "MIT License" not in text


@pytest.mark.unit
def test_readme_tables_use_plain_ascii_apostrophes() -> None:
    text = README.read_text(encoding="utf-8")

    assert "’" not in text
    assert "â€™" not in text
