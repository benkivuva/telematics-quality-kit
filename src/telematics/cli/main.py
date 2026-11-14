"""Command-line dispatch for the embedded vertical slice."""

import argparse
import math
import shlex
import sys
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from threading import Event, Thread

from telematics.backends.simulator import SimulatorBackend
from telematics.cli.doctor import doctor as run_doctor
from telematics.cli.formatting import configure_utf8_stdout
from telematics.cli.init import init_command
from telematics.cli.inject import inject_and_wait
from telematics.cli.session import AttachedSession, EmbeddedSession, create_embedded_session
from telematics.cli.shell import Shell, execute_command, run_script
from telematics.cli.stream import add_stream_parser
from telematics.cli.stream import stream as run_stream
from telematics.clock import ManualClock
from telematics.config import DriftConfig, FreshnessConfig, drift_config_from_environment
from telematics.eval.harness import (
    render_deterministic_results,
    render_eval_results,
    run_deterministic_eval,
    run_model_eval,
)
from telematics.eval.manual import run_manual_eval
from telematics.mcp.server import create_server
from telematics.report.builder import (
    FaultSpec,
    build_report_data,
    load_scenario_file,
    parse_fault_spec,
)
from telematics.report.render import render_report
from telematics.service.vehicles import VehicleService
from telematics.simulator.realtime import SimulatorClockDriver

_SIMULATION_START = datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)


def _demo(*, vehicles: int, seed: int, drift_config: DriftConfig) -> int:
    """Print deterministic before/after output for a stale-device exercise."""
    as_of = datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)
    config = FreshnessConfig()
    baseline_service = VehicleService(
        SimulatorBackend(seed=seed, clock=ManualClock(as_of), vehicles=vehicles),
        config,
        drift_config=drift_config,
    )
    baseline = baseline_service.list_vehicles(as_of=as_of)
    stale_time = as_of - timedelta(seconds=61)
    stale_service = VehicleService(
        SimulatorBackend(seed=seed, clock=ManualClock(stale_time), vehicles=vehicles),
        config,
        drift_config=drift_config,
    )
    after = stale_service.list_vehicles(as_of=as_of)
    print("Phase 2 telematics demo — baseline")
    print("vehicle      verdict  trust score")
    for vehicle in baseline:
        print(
            f"{vehicle.vehicle_id:<12} {vehicle.data_quality.verdict.value:<7}  {vehicle.data_quality.trust_score:.2f}"
        )
    print("after stale-device fault")
    print("vehicle      verdict  trust score")
    for vehicle in after:
        print(
            f"{vehicle.vehicle_id:<12} {vehicle.data_quality.verdict.value:<7} "
            f"{vehicle.data_quality.trust_score:.2f}"
        )
    return 0


def _parse_profile_mix(value: str) -> Mapping[str, int]:
    """Parse a profile mix like ``trk=40,lry=30,car=30``."""
    try:
        parts = value.split(",")
        pairs = [part.split("=", 1) for part in parts]
        if len({pair[0] for pair in pairs}) != len(pairs):
            raise ValueError("profile keys must be unique")
        mix = {key: int(percent) for key, percent in pairs}
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError("profile mix must look like trk=40,lry=30,car=30") from exc
    from telematics.simulator.profiles import assign_profiles

    try:
        assign_profiles(1, mix)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return mix


def _positive_vehicle_count(value: str) -> int:
    count = int(value)
    if not 1 <= count <= 10_000:
        raise argparse.ArgumentTypeError("vehicles must be between 1 and 10000")
    return count


def _port_number(value: str) -> int:
    port = int(value)
    if not 1 <= port <= 65_535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def _parse_speed(value: str) -> float:
    """Parse a positive simulator speed such as ``1x`` or ``60x``."""
    raw = value[:-1] if value.lower().endswith("x") else value
    try:
        speed = float(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("speed must look like 1x or 60x") from exc
    if not math.isfinite(speed) or speed <= 0:
        raise argparse.ArgumentTypeError("speed must be a positive finite value")
    return speed


def _duration_seconds(value: str) -> float:
    """Parse a positive duration written as an integer and s, m, or h."""
    try:
        amount = int(value[:-1])
        scale = {"s": 1, "m": 60, "h": 3600}[value[-1]]
    except (ValueError, IndexError, KeyError) as exc:
        raise argparse.ArgumentTypeError("duration must look like 30s, 6m, or 1h") from exc
    if amount <= 0:
        raise argparse.ArgumentTypeError("duration must be positive")
    return float(amount * scale)


def _positive_detail(value: str) -> int:
    try:
        detail = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("detail must be an integer from 1 to 200") from exc
    if not 1 <= detail <= 200:
        raise argparse.ArgumentTypeError("detail must be between 1 and 200")
    return detail


def _iso_date(value: str) -> date:
    """Parse an evidence date without reading the wall clock."""
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD format") from exc
    if parsed.isoformat() != value:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD format")
    return parsed


def _report(args: argparse.Namespace, *, drift_config: DriftConfig) -> int:
    try:
        scenario = load_scenario_file(args.scenario) if args.scenario else None
        if args.clean and args.inject:
            raise ValueError("--clean cannot be combined with --inject")
        faults: tuple[FaultSpec, ...] | None
        if args.clean:
            faults = ()
        elif scenario is not None or args.inject:
            faults = tuple(scenario.faults if scenario is not None else ()) + tuple(
                parse_fault_spec(item) for item in args.inject
            )
        else:
            faults = None
        seed = args.seed if args.seed is not None else scenario.seed if scenario else 42
        vehicle_count = (
            args.vehicles if args.vehicles is not None else scenario.vehicles if scenario else 12
        )
        duration_seconds = (
            args.duration
            if args.duration is not None
            else scenario.duration.total_seconds()
            if scenario
            else 3600
        )
        profile_mix = (
            args.profile_mix
            if args.profile_mix is not None
            else scenario.profile_mix
            if scenario
            else None
        )
        command_parts = [
            "telematics report",
            f"--vehicles {vehicle_count}",
            f"--seed {seed}",
            f"--duration {int(duration_seconds)}s",
            f"--fault-duration {int(args.fault_duration)}s",
            f"--detail {args.detail}",
        ]
        if args.scenario:
            command_parts.append(f"--scenario {shlex.quote(args.scenario)}")
        elif args.clean:
            command_parts.append("--clean")
        command_parts.extend(f"--inject {shlex.quote(item)}" for item in args.inject)
        if args.profile_mix is not None:
            mix_text = ",".join(f"{key}={value}" for key, value in args.profile_mix.items())
            command_parts.append(f"--profile-mix {mix_text}")
        report_data = build_report_data(
            seed=seed,
            vehicles=vehicle_count,
            duration=timedelta(seconds=duration_seconds),
            fault_duration=timedelta(seconds=args.fault_duration),
            clean=args.clean,
            faults=faults,
            scenario_name=scenario.name if scenario else None,
            detail=args.detail,
            profile_mix=profile_mix,
            command=" ".join(command_parts),
            drift_config=drift_config,
        )
    except (OSError, TypeError, ValueError) as exc:
        print(f"invalid report inputs: {exc}", file=sys.stderr)
        return 2
    html = render_report(report_data)
    target = Path(args.out)
    try:
        target.write_text(html, encoding="utf-8", newline="\n")
    except OSError as exc:
        print(f"cannot write report {target}: {exc}", file=sys.stderr)
        return 4
    size = len(html.encode("utf-8"))
    if size > 5 * 1024 * 1024:
        print(
            f"warning: report is {size} bytes (over 5 MB); lower --detail to reduce its size",
            file=sys.stderr,
        )
    if args.open:
        import webbrowser

        webbrowser.open(target.resolve().as_uri())
    print(f"wrote report to {target}")
    return 0


def _eval(args: argparse.Namespace) -> int:
    """Run the no-key contract eval and, only when requested, the model layer."""
    if args.manual and (args.model is not None or args.out is not None):
        print("--manual cannot be combined with --model or --out", file=sys.stderr)
        return 2
    if (args.out is not None or args.model is not None) and args.run_date is None:
        print("writing eval evidence requires --date YYYY-MM-DD", file=sys.stderr)
        return 2
    result = run_deterministic_eval(seed=args.seed)
    print(
        f"Deterministic eval: {len(result.scenarios)} scenarios, "
        f"{result.assertions_passed}/{result.assertions_total} assertions passed"
    )
    for scenario in result.scenarios:
        failures = [name for name, passed in scenario.assertions if not passed]
        if failures:
            print(f"  FAIL {scenario.name}: {', '.join(failures)}")
        else:
            print(f"  PASS {scenario.name}")
    if not result.passed:
        return 1
    if args.manual:
        manual = run_manual_eval(result)
        print(f"\nManual eval: {manual.passed}/{manual.total} rubric passes")
        print(f"Question-set SHA-256: {manual.question_set_sha256}")
        return 0
    if args.model is None:
        if args.out is not None:
            output = Path(args.out)
            try:
                output.write_text(
                    render_deterministic_results(result, run_date=args.run_date),
                    encoding="utf-8",
                    newline="\n",
                )
            except OSError as exc:
                print(f"cannot write eval results {output}: {exc}", file=sys.stderr)
                return 4
            print(f"Deterministic eval results written to {output}")
        return 0
    try:
        model_result = run_model_eval(args.model, seed=args.seed, run_date=args.run_date)
        output = Path(args.out or "docs/eval-results.md")
        output.write_text(render_eval_results(model_result), encoding="utf-8", newline="\n")
    except ValueError as exc:
        print(f"cannot run model eval: {exc}", file=sys.stderr)
        return 2
    except (OSError, RuntimeError) as exc:
        print(f"model eval failed: {exc}", file=sys.stderr)
        return 4
    print(f"Model eval results written to {output}")
    return 0


def _shell(
    *,
    vehicles: int,
    seed: int,
    profile_mix: Mapping[str, int] | None,
    attach: str | None,
    command: str | None,
    script: str | None,
    drift_config: DriftConfig,
) -> int:
    session: EmbeddedSession | AttachedSession
    if attach is None:
        session = create_embedded_session(
            vehicles=vehicles,
            seed=seed,
            start=_SIMULATION_START,
            profile_mix=dict(profile_mix) if profile_mix is not None else None,
            drift_config=drift_config,
        )
        session.advance(timedelta(minutes=10))
    else:
        session = AttachedSession(attach)
    if command is not None:
        return execute_command(session, command)
    shell = Shell(session)
    if script is not None:
        try:
            contents = Path(script).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"cannot read script {script}: {exc}", file=sys.stderr)
            return 4
        return run_script(shell, contents)
    if isinstance(session, EmbeddedSession):
        stop = Event()
        clock_thread = Thread(
            target=session.clock_driver.run,
            args=(stop,),
            daemon=True,
        )
        clock_thread.start()
        try:
            try:
                shell.cmdloop()
            except KeyboardInterrupt:
                print("\nInterrupted; exiting shell.")
        finally:
            stop.set()
            clock_thread.join()
    else:
        try:
            shell.cmdloop()
        except KeyboardInterrupt:
            print("\nInterrupted; exiting shell.")
    return 0


def _serve(
    *,
    vehicles: int,
    seed: int,
    profile_mix: Mapping[str, int] | None,
    transport: str,
    host: str,
    port: int,
    drift_config: DriftConfig,
    speed: float = 1.0,
) -> int:
    """Run the embedded simulated fleet over the selected MCP transport."""
    clock = ManualClock(_SIMULATION_START)
    backend = SimulatorBackend(
        seed=seed,
        clock=clock,
        vehicles=vehicles,
        profile_mix=profile_mix,
    )
    service = VehicleService(backend, FreshnessConfig(), drift_config=drift_config)
    server = create_server(service, as_of=clock.now(), clock=clock)
    stop = Event()
    driver = SimulatorClockDriver(backend, speed=speed)
    clock_thread = Thread(target=driver.run, args=(stop,), daemon=True)
    clock_thread.start()
    try:
        if transport == "stdio":
            server.run(transport="stdio")
        else:
            server.run(transport="streamable-http", host=host, port=port)
    finally:
        stop.set()
        clock_thread.join()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse the supported command and return its process exit code."""
    configure_utf8_stdout()
    parser = argparse.ArgumentParser(prog="telematics")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="run the deterministic vertical-slice demo")
    demo.add_argument("--vehicles", type=_positive_vehicle_count, default=3)
    demo.add_argument("--seed", type=int, default=42)
    serve = commands.add_parser("serve", help="serve a synthetic fleet over MCP")
    serve.add_argument("--vehicles", type=_positive_vehicle_count, default=12)
    serve.add_argument("--seed", type=int, default=42)
    serve.add_argument("--profile-mix", type=_parse_profile_mix)
    serve.add_argument(
        "--transport", choices=("stdio", "streamable-http"), default="streamable-http"
    )
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=_port_number, default=8000)
    serve.add_argument("--speed", type=_parse_speed, default=1.0)
    shell_parser = commands.add_parser("shell", help="open the developer command shell")
    shell_parser.add_argument("--vehicles", type=_positive_vehicle_count, default=12)
    shell_parser.add_argument("--seed", type=int, default=42)
    shell_parser.add_argument("--profile-mix", type=_parse_profile_mix)
    shell_parser.add_argument(
        "--attach", nargs="?", const="http://127.0.0.1:8000/mcp", metavar="URL"
    )
    shell_mode = shell_parser.add_mutually_exclusive_group()
    shell_mode.add_argument("-c", dest="shell_command")
    shell_mode.add_argument("--script")
    inject = commands.add_parser("inject", help="inject a fault into an attached simulator")
    inject.add_argument("fault")
    inject.add_argument("--vehicle", required=True)
    inject.add_argument("--severity", choices=("low", "medium", "high"), default="medium")
    inject.add_argument("--duration")
    inject.add_argument("--url", default="http://127.0.0.1:8000/mcp")
    inject.add_argument("--wait", nargs="?", const="30s", type=_duration_seconds)
    inject.add_argument("--expect", choices=("PASS", "WARN", "BLOCK"), default="BLOCK")
    add_stream_parser(commands)
    init_parser = commands.add_parser("init", help="write or print a starter template")
    init_parser.add_argument("template", choices=("fleet", "scenario", "script"))
    init_parser.add_argument("path", nargs="?")
    commands.add_parser("doctor", help="check the local development environment")
    report = commands.add_parser("report", help="write a self-contained static fleet report")
    report.add_argument("--vehicles", type=_positive_vehicle_count)
    report.add_argument("--seed", type=int)
    report_source = report.add_mutually_exclusive_group()
    report_source.add_argument("--scenario")
    report_source.add_argument("--clean", action="store_true")
    report.add_argument("--inject", action="append", default=[])
    report.add_argument("--duration", type=_duration_seconds)
    report.add_argument("--fault-duration", type=_duration_seconds, default=1200.0)
    report.add_argument("--detail", type=_positive_detail, default=50)
    report.add_argument("--profile-mix", type=_parse_profile_mix)
    report.add_argument("--out", default="fleet-report.html")
    report.add_argument("--open", action="store_true")
    eval_parser = commands.add_parser("eval", help="run deterministic and optional model evals")
    eval_parser.add_argument("--seed", type=int, default=42)
    eval_parser.add_argument(
        "--model", help="optional Gemini model identifier; requires an API key"
    )
    eval_parser.add_argument("--out", help="write evaluation evidence to this Markdown path")
    eval_parser.add_argument("--date", dest="run_date", type=_iso_date)
    eval_parser.add_argument(
        "--manual",
        action="store_true",
        help="run the interactive no-key rubric over the fixed scenarios",
    )
    args = parser.parse_args(argv)
    drift_config: DriftConfig | None = None
    if args.command in {"demo", "serve", "shell", "stream", "report"}:
        try:
            drift_config = drift_config_from_environment()
        except ValueError as exc:
            parser.error(str(exc))
    if args.command == "demo":
        assert drift_config is not None
        return _demo(vehicles=args.vehicles, seed=args.seed, drift_config=drift_config)
    if args.command == "serve":
        assert drift_config is not None
        return _serve(
            vehicles=args.vehicles,
            seed=args.seed,
            profile_mix=args.profile_mix,
            transport=args.transport,
            host=args.host,
            port=args.port,
            speed=args.speed,
            drift_config=drift_config,
        )
    if args.command == "shell":
        assert drift_config is not None
        return _shell(
            vehicles=args.vehicles,
            seed=args.seed,
            profile_mix=args.profile_mix,
            attach=args.attach,
            command=args.shell_command,
            script=args.script,
            drift_config=drift_config,
        )
    if args.command == "inject":
        return inject_and_wait(
            AttachedSession(args.url),
            fault=args.fault,
            vehicle_id=args.vehicle,
            severity=args.severity,
            duration=args.duration,
            expected=args.expect,
            timeout_seconds=args.wait,
        )
    if args.command == "stream":
        assert drift_config is not None
        if args.rate < 1:
            parser.error("stream rate must be positive")
        return run_stream(
            vehicles=args.vehicles,
            seed=args.seed,
            rate=args.rate,
            vehicle_id=args.vehicle,
            stages=set(args.stage) if args.stage else None,
            issues_only=args.issues_only,
            show_hex=args.hex,
            as_json=args.json,
            drift_config=drift_config,
        )
    if args.command == "init":
        return init_command(args.template, args.path)
    if args.command == "doctor":
        return run_doctor()
    if args.command == "report":
        assert drift_config is not None
        return _report(args, drift_config=drift_config)
    if args.command == "eval":
        return _eval(args)
    return 0
