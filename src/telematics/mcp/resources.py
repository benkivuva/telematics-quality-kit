"""Read-only MCP resources for quality semantics and simulator profiles."""

import json

from mcp.server.mcpserver import MCPServer

from telematics.config import DriftConfig, DuplicatesConfig, FreshnessConfig, FuelConfig
from telematics.simulator.profiles import PROFILES


def register_resources(server: MCPServer) -> None:
    """Register the stable quality and profile resources."""

    @server.resource(
        "quality://checks",
        name="quality-checks",
        description="Quality checks, heuristic defaults, scores, and verdict policy.",
        mime_type="application/json",
    )
    def quality_checks() -> str:
        return json.dumps(
            {
                "checks": [
                    {
                        "name": "freshness",
                        "defaults": {
                            "expected_interval_seconds": FreshnessConfig().expected_interval_seconds,
                            "warn_after_intervals": FreshnessConfig().warn_after_intervals,
                            "block_after_intervals": FreshnessConfig().block_after_intervals,
                        },
                    },
                    {
                        "name": "drift",
                        "defaults": {
                            "warn_fraction": DriftConfig().warn_fraction,
                            "block_fraction": DriftConfig().block_fraction,
                        },
                    },
                    {
                        "name": "duplicates",
                        "defaults": {
                            "warn_fraction": DuplicatesConfig().warn_fraction,
                            "block_fraction": DuplicatesConfig().block_fraction,
                        },
                    },
                    {"name": "ignition", "defaults": {"transitions": "more than 4 in 120 seconds"}},
                    {
                        "name": "plausibility",
                        "defaults": {
                            "warn_clock_skew_seconds": 300,
                            "block_clock_skew_seconds": 3600,
                        },
                    },
                    {
                        "name": "fuel",
                        "defaults": {
                            "unexplained_drop_percent": FuelConfig().unexplained_drop_percent
                        },
                    },
                ],
                "verdict_labels": {
                    "PASS": "trust it",
                    "WARN": "be careful",
                    "BLOCK": "don't trust it",
                },
            },
            sort_keys=True,
        )

    @server.resource(
        "fleet://profiles",
        name="fleet-profiles",
        description="Synthetic Kenya fleet profiles and protocol assignments.",
        mime_type="application/json",
    )
    def fleet_profiles() -> str:
        return json.dumps(
            {
                code: {
                    "name": profile.name,
                    "max_speed_kph": profile.max_speed_kph,
                    "report_interval_seconds": profile.report_interval_seconds,
                    "protocol": profile.protocol,
                    "route": profile.route,
                }
                for code, profile in PROFILES.items()
            },
            sort_keys=True,
        )
