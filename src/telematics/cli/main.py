"""Command-line dispatch for the embedded vertical slice."""

import argparse
from datetime import UTC, datetime, timedelta

from telematics.backends.simulator import SimulatorBackend
from telematics.clock import ManualClock
from telematics.config import FreshnessConfig
from telematics.service.vehicles import VehicleService


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


def main(argv: list[str] | None = None) -> int:
    """Parse the supported command and return its process exit code."""
    parser = argparse.ArgumentParser(prog="telematics")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="run the deterministic vertical-slice demo")
    demo.add_argument("--vehicles", type=int, default=3)
    demo.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    if args.command == "demo":
        return _demo(vehicles=args.vehicles, seed=args.seed)
    return 0
