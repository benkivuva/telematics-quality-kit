"""Invariant 12: on stdio, stdout carries JSON-RPC only and logs go to stderr."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).parents[2]
_INITIALIZE: dict[str, Any] = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "stdio-contract-test", "version": "0.0"},
    },
}


def test_stdio_stdout_contains_only_jsonrpc_and_logs_go_to_stderr() -> None:
    server_code = (
        "from telematics.cli.main import main; "
        "raise SystemExit(main(['serve', '--vehicles', '1', '--seed', '42', "
        "'--transport', 'stdio']))"
    )
    payload = (
        json.dumps(_INITIALIZE)
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
        + "\n"
    )

    completed = subprocess.run(
        [sys.executable, "-c", server_code],
        input=payload,
        text=True,
        capture_output=True,
        cwd=_PROJECT_ROOT,
        env={
            key: value
            for key, value in os.environ.items()
            if not key.startswith("COV_CORE") and key != "COVERAGE_PROCESS_START"
        },
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0
    stdout_lines = [line for line in completed.stdout.splitlines() if line.strip()]
    assert stdout_lines, "the server produced no JSON-RPC response"

    messages = [json.loads(line) for line in stdout_lines]
    assert all(message["jsonrpc"] == "2.0" for message in messages)
    assert any(message.get("id") == 1 and "result" in message for message in messages)
    assert "serving 1 vehicles over stdio" in completed.stderr
    assert "logs on stderr" in completed.stderr
    assert "serving 1 vehicles over stdio" not in completed.stdout
