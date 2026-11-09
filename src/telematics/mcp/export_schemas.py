"""Export MCP output schemas for clients outside Python."""

import json
from pathlib import Path

from telematics.mcp.schemas import TOOL_OUTPUT_MODELS


def write_output_schemas(destination: Path) -> tuple[Path, ...]:
    """Write one stable JSON Schema per tool and return the written paths."""
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for tool_name, model in TOOL_OUTPUT_MODELS.items():
        target = destination / f"{tool_name}.json"
        target.write_text(
            json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written.append(target)
    return tuple(written)
