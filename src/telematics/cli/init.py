"""Safe starter templates for fleet, scenario, and shell-script files."""

from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import yaml  # type: ignore[import-untyped]

TemplateKind = Literal["fleet", "scenario", "script"]

_TEMPLATES: Mapping[TemplateKind, str] = {
    "fleet": """# Synthetic fleet profile mix; percentages must sum to 100.
seed: 42
vehicles: 12
profile_mix:
  trk: 40
  lry: 30
  car: 30
""",
    "scenario": """# A small simulator drill definition.
name: blackout-drill
seed: 42
vehicles: 12
duration: 1h
faults:
  - fault: rural_blackout
    vehicle_id: TRK-0001
    severity: medium
""",
    "script": """# Run with: telematics shell --script drill.tqs
fleet
expect verdict TRK-0001 PASS
""",
}

_DEFAULT_NAMES: Mapping[TemplateKind, str] = {
    "fleet": "fleet.yaml",
    "scenario": "scenario.yaml",
    "script": "drill.tqs",
}


def render_template(kind: TemplateKind) -> str:
    """Return a deterministic starter file for one supported template kind."""
    try:
        contents = _TEMPLATES[kind]
    except KeyError as exc:
        raise ValueError(f"unknown template kind: {kind}") from exc
    load_template(kind, contents)
    return contents


def load_template(kind: TemplateKind, contents: str) -> dict[str, object] | tuple[str, ...]:
    """Round-trip a YAML template with safe_load or parse shell commands."""
    if kind == "script":
        commands = tuple(
            line.strip()
            for line in contents.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
        if not commands:
            raise ValueError("script template contains no commands")
        return commands
    if kind not in {"fleet", "scenario"}:
        raise ValueError(f"unknown template kind: {kind}")
    loaded = yaml.safe_load(contents)
    if not isinstance(loaded, dict) or not all(isinstance(key, str) for key in loaded):
        raise ValueError(f"{kind} template must contain a YAML mapping")
    return loaded


def write_template(kind: TemplateKind, path: str | Path | None = None) -> Path:
    """Write a starter file without overwriting an existing path."""
    target = Path(path) if path is not None else Path(_DEFAULT_NAMES[kind])
    contents = render_template(kind)
    with target.open("x", encoding="utf-8", newline="\n") as output:
        output.write(contents)
    return target


def init_command(kind: TemplateKind, path: str | None = None) -> int:
    """CLI action for printing a template or writing it to a new file."""
    if path is None:
        print(render_template(kind), end="")
        return 0
    try:
        target = write_template(kind, path)
    except FileExistsError:
        print(f"refusing to overwrite {path}; choose another path")
        return 2
    except OSError as exc:
        print(f"cannot write template {path}: {exc}")
        return 4
    print(f"wrote {kind} template to {target}")
    return 0
