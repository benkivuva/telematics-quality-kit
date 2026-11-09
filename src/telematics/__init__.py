"""Telematics data quality testbed."""

from __future__ import annotations

import argparse


def main() -> None:
    """Show the command line entry point help."""
    parser = argparse.ArgumentParser(
        prog="telematics",
        description="A deterministic testbed for telematics data quality.",
    )
    parser.parse_args()

