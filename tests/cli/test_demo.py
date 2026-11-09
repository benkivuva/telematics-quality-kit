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


@pytest.mark.unit
def test_demo_output_is_byte_identical_for_the_same_seed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main(["demo", "--vehicles", "3", "--seed", "42"])
    first = capsys.readouterr().out.encode()
    main(["demo", "--vehicles", "3", "--seed", "42"])
    second = capsys.readouterr().out.encode()

    assert first == second
