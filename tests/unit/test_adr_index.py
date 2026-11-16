"""The ADR index and the ``docs/adr`` filenames must agree, with no collisions."""

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).parents[2]
_ADR_DIR = _ROOT / "docs" / "adr"
_INDEX_HEADING = "## 20. Decision log (ADR index)"
_NEXT_HEADING = "## 21. Sources and open verification items"


def _indexed_numbers() -> list[int]:
    text = (_ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    section = text.split(_INDEX_HEADING, 1)[1].split(_NEXT_HEADING, 1)[0]
    return [int(number) for number in re.findall(r"^\| (\d{4}) \|", section, re.MULTILINE)]


@pytest.mark.unit
def test_adr_index_is_contiguous_and_each_number_has_one_file() -> None:
    numbers = _indexed_numbers()

    assert numbers == list(range(1, len(numbers) + 1))
    for number in numbers:
        matches = sorted(_ADR_DIR.glob(f"{number:04d}-*.md"))
        assert len(matches) == 1, f"ADR {number:04d} has {len(matches)} files: {matches}"
        first_line = matches[0].read_text(encoding="utf-8").splitlines()[0]
        assert first_line.startswith(f"# ADR {number:04d}:")


@pytest.mark.unit
def test_no_adr_file_is_missing_from_the_index() -> None:
    indexed = set(_indexed_numbers())
    on_disk = {int(path.name[:4]) for path in _ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md")}

    assert on_disk == indexed
