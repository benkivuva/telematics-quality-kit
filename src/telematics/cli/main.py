"""Command-line dispatch for the embedded vertical slice."""

import argparse
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from telematics.backends.simulator import SimulatorBackend
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
    server = create_server(service, as_of=clock.now())
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
    return 0
