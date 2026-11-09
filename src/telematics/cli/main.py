"""Command-line dispatch for the embedded vertical slice."""

import argparse
import sys
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

from telematics.backends.simulator import SimulatorBackend
from telematics.cli.inject import inject_and_wait
from telematics.cli.session import AttachedSession, EmbeddedSession, create_embedded_session
from telematics.cli.shell import Shell, execute_command, run_script
from telematics.clock import ManualClock
from telematics.config import FreshnessConfig
from telematics.mcp.server import create_server
from telematics.service.vehicles import VehicleService

_SIMULATION_START = datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)


def _demo(*, vehicles: int, seed: int) -> int:
    """Print deterministic before/after output for a stale-device exercise."""
    as_of = datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC)
    config = FreshnessConfig()
    baseline_service = VehicleService(
        SimulatorBackend(seed=seed, clock=ManualClock(as_of), vehicles=vehicles), config
    )
    baseline = baseline_service.list_vehicles(as_of=as_of)
    stale_time = as_of - timedelta(seconds=61)
    stale_service = VehicleService(
        SimulatorBackend(seed=seed, clock=ManualClock(stale_time), vehicles=vehicles), config
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


def _shell(
    *,
    vehicles: int,
    seed: int,
    profile_mix: Mapping[str, int] | None,
    attach: str | None,
    command: str | None,
    script: str | None,
) -> int:
    session: EmbeddedSession | AttachedSession
    if attach is None:
        session = create_embedded_session(
            vehicles=vehicles,
            seed=seed,
            start=_SIMULATION_START,
            profile_mix=dict(profile_mix) if profile_mix is not None else None,
        )
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
    shell.cmdloop()
    return 0


def _serve(
    *,
    vehicles: int,
    seed: int,
    profile_mix: Mapping[str, int] | None,
    transport: str,
    host: str,
    port: int,
) -> int:
    """Run the embedded simulated fleet over the selected MCP transport."""
    clock = ManualClock(_SIMULATION_START)
    backend = SimulatorBackend(
        seed=seed,
        clock=clock,
        vehicles=vehicles,
        profile_mix=profile_mix,
    )
    service = VehicleService(backend, FreshnessConfig())
    server = create_server(service, as_of=clock.now(), clock=clock)
    if transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport="streamable-http", host=host, port=port)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse the supported command and return its process exit code."""
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
    args = parser.parse_args(argv)
    if args.command == "demo":
        return _demo(vehicles=args.vehicles, seed=args.seed)
    if args.command == "serve":
        return _serve(
            vehicles=args.vehicles,
            seed=args.seed,
            profile_mix=args.profile_mix,
            transport=args.transport,
            host=args.host,
            port=args.port,
        )
    if args.command == "shell":
        return _shell(
            vehicles=args.vehicles,
            seed=args.seed,
            profile_mix=args.profile_mix,
            attach=args.attach,
            command=args.shell_command,
            script=args.script,
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
    return 0
