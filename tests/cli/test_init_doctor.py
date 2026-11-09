"""Round-trip tests for starter templates and environment diagnosis."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from telematics.cli import main as cli_main
from telematics.cli.doctor import diagnose_environment
from telematics.cli.init import load_template, render_template, write_template
from telematics.cli.session import create_embedded_session
from telematics.cli.shell import Shell, run_script


@pytest.mark.parametrize("kind", ["fleet", "scenario"])
def test_yaml_templates_round_trip_with_safe_loader(kind: str) -> None:
    contents = render_template(kind)

    loaded = load_template(kind, contents)

    assert isinstance(loaded, dict)
    assert loaded
    assert "!!python" not in contents


def test_script_template_runs_without_edits() -> None:
    contents = render_template("script")
    shell = Shell(
        create_embedded_session(
            vehicles=1,
            seed=42,
            start=datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC),
        )
    )

    assert run_script(shell, contents) == 0


def test_template_writer_refuses_to_overwrite_and_writes_utf8(tmp_path: Path) -> None:
    target = tmp_path / "fleet.yaml"

    written = write_template("fleet", target)

    assert written == target
    assert load_template("fleet", target.read_text(encoding="utf-8"))
    with pytest.raises(FileExistsError):
        write_template("fleet", target)


def test_safe_loader_rejects_python_object_tags() -> None:
    with pytest.raises(yaml.YAMLError):
        load_template("fleet", "!!python/object/apply:os.system ['echo unsafe']")


@pytest.mark.unit
def test_doctor_lists_a_one_line_fix_for_each_failure() -> None:
    result = diagnose_environment(
        python_version=(3, 11, 9), uv_available=False, package_available=False
    )

    assert len(result) == 3
    assert all(line.startswith("FAIL ") and "—" in line for line in result)


@pytest.mark.unit
def test_doctor_reports_success_checks_without_failures() -> None:
    result = diagnose_environment(
        python_version=(3, 12, 1), uv_available=True, package_available=True
    )

    assert result == ("OK Python 3.12+", "OK uv available", "OK package installed")


def test_main_dispatches_init_and_doctor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "scenario.yaml"

    assert cli_main.main(["init", "scenario", str(target)]) == 0
    assert load_template("scenario", target.read_text(encoding="utf-8"))
    assert cli_main.main(["doctor"]) in {0, 1}
    assert capsys.readouterr().out.count("\n") >= 4


def test_template_write_failure_returns_internal_error_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing_path = tmp_path / "missing" / "fleet.yaml"

    status = cli_main.main(["init", "fleet", str(missing_path)])

    assert status == 4
    assert "cannot write template" in capsys.readouterr().out


def test_usage_errors_keep_argparse_exit_code_two() -> None:
    with pytest.raises(SystemExit) as raised:
        cli_main.main(["report", "--vehicles", "0"])

    assert raised.value.code == 2
