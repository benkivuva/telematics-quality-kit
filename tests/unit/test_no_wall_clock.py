"""Output-affecting modules must use the injected Clock."""

import re
from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).parents[2] / "src" / "telematics"
WALL_CLOCK_CALL = re.compile(r"\b(?:time\.time|datetime\.now)\s*\(")


@pytest.mark.unit
def test_output_affecting_modules_do_not_read_the_wall_clock() -> None:
    violations = [
        str(path.relative_to(SOURCE_ROOT))
        for path in SOURCE_ROOT.rglob("*.py")
        if WALL_CLOCK_CALL.search(path.read_text(encoding="utf-8"))
    ]

    assert violations == []
