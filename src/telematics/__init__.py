"""Telematics data quality testbed."""

from __future__ import annotations

from telematics.cli.main import main as _cli_main


def main() -> int:
    """Run the telematics command line interface."""
    return _cli_main()
