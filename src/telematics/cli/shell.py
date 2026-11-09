"""Portable ``cmd.Cmd`` shell for embedded and attached MCP sessions."""

import cmd
import json
import shlex
import sys
from collections import Counter
from datetime import timedelta
from typing import Any, TextIO

from telematics.cli.formatting import json_line, render_verdict
from telematics.cli.session import AttachedSession, EmbeddedSession
from telematics.models.quality import Verdict

_ALIASES = {
    "stale": "stale_device",
    "drift": "gps_drift",
    "blackout": "rural_blackout",
    "dupes": "duplicate_heartbeats",
    "flicker": "ignition_flicker",
    "skew": "clock_skew",
    "fuel-spike": "fuel_sensor_spike",
    "burst": "buffered_burst",
}


def _duration(value: str) -> timedelta:
    if len(value) < 2 or not value[:-1].isdigit() or int(value[:-1]) <= 0:
        raise ValueError("duration must be a positive integer followed by s, m, or h")
    amount, unit = int(value[:-1]), value[-1]
    scale = {"s": 1, "m": 60, "h": 3600}.get(unit)
    if scale is None:
        raise ValueError("duration must end in s, m, or h")
    return timedelta(seconds=amount * scale)


class Shell(cmd.Cmd):
    """One command dispatcher shared by interactive and scripted sessions."""

    intro = "Telematics quality shell. Type help for commands."
    prompt = "telematics> "

    def __init__(
        self,
        session: EmbeddedSession | AttachedSession,
        *,
        stdin: TextIO | None = None,
        stdout: TextIO | None = None,
    ) -> None:
        super().__init__(stdin=stdin or sys.stdin, stdout=stdout or sys.stdout)
        self.session = session
        self.use_rawinput = stdin is None
        self.failed = False
        self.failure_message = ""
        self.last_result: dict[str, Any] | None = None

    def _call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        try:
            result = self.session.call_tool(name, arguments)
        except (RuntimeError, ValueError) as exc:
            self._write(f"error: {exc}")
            return None
        self.last_result = result
        return result

    def _write(self, value: str) -> None:
        self.stdout.write(value + "\n")

    def default(self, line: str) -> None:
        self.failed = True
        self.failure_message = f"unknown command: {line.split(maxsplit=1)[0]}"
        self._write(self.failure_message)

    def do_fleet(self, _argument: str) -> None:
        """Show fleet trust score and verdict counts."""
        result = self._call("get_quality_report", {"verbose": False})
        if result is None:
            return
        vehicles = result.get("vehicles", [])
        counts = Counter(item["data_quality"]["verdict"] for item in vehicles)
        score = float(result.get("fleet_trust_score", 1.0))
        self._write(
            f"{len(vehicles)} vehicles · fleet trust {score:.2f} · "
            f"PASS {counts['PASS']} WARN {counts['WARN']} BLOCK {counts['BLOCK']}"
        )

    def do_ls(self, argument: str) -> None:
        """List vehicles, worst quality first: ls [--limit N]."""
        try:
            tokens = shlex.split(argument)
            limit = int(tokens[tokens.index("--limit") + 1]) if "--limit" in tokens else 50
            result = self._call("list_vehicles", {"limit": limit})
        except (ValueError, IndexError) as exc:
            self._write(f"usage: ls [--limit 1..200] ({exc})")
            return
        if result is None:
            return
        vehicles = result.get("vehicles", [])
        vehicles.sort(key=lambda item: (item["data_quality"]["trust_score"], item["vehicle_id"]))
        for item in vehicles:
            quality = item["data_quality"]
            verdict = Verdict(quality["verdict"])
            self._write(
                f"{item['vehicle_id']:<12} {render_verdict(verdict)} {quality['trust_score']:.2f}"
            )

    def do_get(self, argument: str) -> None:
        """Show one latest location: get VEHICLE_ID."""
        try:
            (vehicle_id,) = shlex.split(argument)
        except ValueError:
            self._write("usage: get VEHICLE_ID")
            return
        result = self._call("get_vehicle_location", {"vehicle_id": vehicle_id})
        if result is None:
            return
        quality = result["data_quality"]
        verdict = Verdict(quality["verdict"])
        self._write(
            f"{vehicle_id} {result['latitude']:.5f}, {result['longitude']:.5f} · "
            f"age {result['age_seconds']}s · {render_verdict(verdict)} · "
            f"usable_for_decision={quality['usable_for_decision']}"
        )
        for caveat in quality["caveats"]:
            self._write(f"caveat: {caveat}")

    def do_report(self, argument: str) -> None:
        """Show a quality report: report [VEHICLE_ID] [--verbose]."""
        try:
            tokens = shlex.split(argument)
        except ValueError as exc:
            self._write(f"usage: report [VEHICLE_ID] [--verbose] ({exc})")
            return
        vehicle_id = next((token for token in tokens if not token.startswith("--")), None)
        result = self._call(
            "get_quality_report",
            {"vehicle_id": vehicle_id, "verbose": "--verbose" in tokens},
        )
        if result is not None:
            self._write(json_line(result))

    def do_explain(self, argument: str) -> None:
        """Explain one check: explain VEHICLE_ID CHECK."""
        try:
            vehicle_id, check_name = shlex.split(argument)
        except ValueError:
            self._write("usage: explain VEHICLE_ID CHECK")
            return
        result = self._call("get_quality_report", {"vehicle_id": vehicle_id, "verbose": True})
        if result is None:
            return
        vehicles = result.get("vehicles", [])
        if not vehicles:
            self._write(f"vehicle not found: {vehicle_id}")
            return
        checks = vehicles[0]["data_quality"]["checks"]
        check = next((item for item in checks if item["name"] == check_name), None)
        if check is None:
            self._write(f"unknown check: {check_name}")
            return
        self._write(
            f"{check_name} {check['verdict']} · score {check['score']:.2f} · "
            f"metrics {json_line(check['metric'])}"
        )

    def do_call(self, argument: str) -> None:
        """Call any public MCP tool: call TOOL [JSON_ARGUMENTS]."""
        name, separator, raw = argument.partition(" ")
        if not name:
            self._write("usage: call TOOL [JSON_ARGUMENTS]")
            return
        try:
            values = json.loads(raw) if separator and raw.strip() else {}
            if not isinstance(values, dict):
                raise TypeError("tool arguments must be a JSON object")
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            self._write(f"invalid JSON arguments: {exc}")
            return
        result = self._call(name, values)
        if result is not None:
            self._write(json_line(result))

    def do_tools(self, _argument: str) -> None:
        """List tools exposed by the active MCP server."""
        try:
            tools = self.session.list_tools()
        except (RuntimeError, ValueError) as exc:
            self._write(f"error: {exc}")
            return
        for tool in tools:
            self._write(f"{tool['name']} — {tool['description']}")

    def do_inject(self, argument: str) -> None:
        """Inject a simulator fault: inject FAULT VEHICLE [--severity LEVEL]."""
        try:
            tokens = shlex.split(argument)
            fault, vehicle_id = tokens[0], tokens[1]
            fault = _ALIASES.get(fault, fault)
            severity = (
                tokens[tokens.index("--severity") + 1] if "--severity" in tokens else "medium"
            )
            params: dict[str, str] = {"severity": severity}
            if "--duration" in tokens:
                params["duration"] = tokens[tokens.index("--duration") + 1]
            result = self._call(
                "inject_fault", {"vehicle_id": vehicle_id, "fault": fault, "params": params}
            )
        except (ValueError, IndexError) as exc:
            self._write(
                "usage: inject FAULT VEHICLE_ID [--severity low|medium|high] "
                f"[--duration 15m] ({exc})"
            )
            return
        if result is not None:
            self._write(f"{result['fault']} on {vehicle_id} ({severity}) [{result['fault_id']}]")
            self._write(f"expected: {result['expected_quality_impact']}")

    def do_clear(self, _argument: str) -> None:
        """Clear simulator faults with the public reset tool."""
        result = self._call("reset_simulator", {})
        if result is not None:
            self._write(f"cleared {result['cleared_faults']} simulator faults")

    def do_faults(self, _argument: str) -> None:
        """Show active embedded simulator fault IDs."""
        if isinstance(self.session, EmbeddedSession):
            active = self.session.backend._active_faults
            for fault_id, fault in active.items():
                self._write(f"{fault_id} {fault.name} {fault.vehicle_id}")
            if not active:
                self._write("no active faults")
        else:
            self._write("active fault listing is available only in embedded mode")

    def do_advance(self, argument: str) -> None:
        """Advance embedded simulated time: advance 6m."""
        try:
            duration = _duration(argument.strip())
            at = self.session.advance(duration)
        except (ValueError, RuntimeError, TypeError) as exc:
            self._write(f"error: {exc}")
            return
        self._write(f"sim time {at.isoformat()}")

    def do_expect(self, argument: str) -> None:
        """Assert a verdict or field: expect verdict ID BLOCK | expect field ID PATH VALUE."""
        try:
            tokens = shlex.split(argument)
            kind = tokens[0]
            if kind == "verdict" and len(tokens) == 3:
                _, vehicle_id, expected_raw = tokens
                actual = self._call("get_vehicle_location", {"vehicle_id": vehicle_id})
                observed = actual["data_quality"]["verdict"] if actual is not None else None
                expected: object = expected_raw
            elif kind == "field" and len(tokens) == 4:
                _, vehicle_id, path, expected_raw = tokens
                actual = self._call("get_vehicle_location", {"vehicle_id": vehicle_id})
                observed = actual
                for key in path.split("."):
                    observed = observed[key] if isinstance(observed, dict) else None
                expected = {"true": True, "false": False}.get(expected_raw.lower(), expected_raw)
            else:
                raise ValueError("expected verdict ID VALUE or field ID PATH VALUE")
        except (ValueError, IndexError, KeyError) as exc:
            self.failed = True
            self.failure_message = str(exc)
            self._write(f"expectation failed: {exc}")
            return
        if observed != expected:
            self.failed = True
            self.failure_message = f"expected {expected!r}, observed {observed!r}"
            self._write(f"expectation failed: {self.failure_message}")
        else:
            self._write(f"expectation passed: {observed}")

    def do_exit(self, _argument: str) -> bool:
        """Exit the shell."""
        return True

    do_quit = do_exit

    def do_EOF(self, _argument: str) -> bool:
        """Exit on end of input."""
        self._write("")
        return True


def run_script(shell: Shell, contents: str) -> int:
    """Execute a shell script and report the first failed expectation line."""
    for line_number, line in enumerate(contents.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        shell.failed = False
        shell.failure_message = ""
        should_stop = shell.onecmd(stripped)
        if shell.failed:
            shell._write(f"line {line_number} failed: {shell.failure_message}")
            return 1
        if should_stop:
            break
    return 0


def execute_command(
    session: EmbeddedSession | AttachedSession,
    command: str,
    *,
    stdout: TextIO | None = None,
) -> int:
    """Execute one ``-c`` command and return its shell status."""
    shell = Shell(session, stdout=stdout)
    shell.onecmd(command)
    return 1 if shell.failed else 0
