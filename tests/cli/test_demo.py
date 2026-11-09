"""Embedded demo CLI contract tests."""

import pytest

from telematics.cli.main import main


@pytest.mark.unit
def test_demo_prints_before_and_after_and_returns_success(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["demo", "--vehicles", "1", "--seed", "42"]) == 0
    output = capsys.readouterr().out
    assert "baseline" in output.lower()
    assert "after" in output.lower()
