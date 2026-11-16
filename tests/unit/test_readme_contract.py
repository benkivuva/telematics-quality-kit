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


@pytest.mark.unit
def test_readme_has_no_double_encoded_utf8() -> None:
    text = README.read_text(encoding="utf-8")

    for marker in ("â", "Ã"):
        assert marker not in text, f"README contains double-encoded UTF-8 marker {marker!r}"
