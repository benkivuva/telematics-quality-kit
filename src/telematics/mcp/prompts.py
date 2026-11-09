"""Guided MCP prompts for common fleet-quality workflows."""

from mcp.server.mcpserver import MCPServer


def register_prompts(server: MCPServer) -> None:
    """Register the three v0.1 demonstration prompts."""

    @server.prompt(name="fleet_health_briefing")
    def fleet_health_briefing() -> str:
        """Summarize fleet quality and call out blocked vehicles."""
        return (
            "Call get_quality_report for the fleet. Summarize PASS, WARN, and BLOCK counts, "
            "relay each data_quality label, and explain caveats without treating BLOCK as an error."
        )

    @server.prompt(name="investigate_vehicle")
    def investigate_vehicle(vehicle_id: str) -> str:
        """Investigate a vehicle's latest location and quality checks."""
        return (
            f"Investigate {vehicle_id}. Call get_vehicle_location and get_quality_report, "
            "then explain the check metrics and any withheld values."
        )

    @server.prompt(name="fault_drill")
    def fault_drill(vehicle_id: str) -> str:
        """Run a reversible simulator-only quality fault drill."""
        return (
            f"For simulator backend {vehicle_id}, first inspect get_quality_report, then use "
            "inject_fault with a fault that matches the failure being demonstrated. Compare "
            "the expected impact and final quality report; call reset_simulator afterwards."
        )
