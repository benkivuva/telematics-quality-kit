"""Shared CLI formatting for text-first verdicts and structured output."""

import json
import os
import sys
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel

from telematics.models.quality import Verdict

_EAT = timezone(timedelta(hours=3))

_LABELS = {
    Verdict.PASS: ("✓", "trust it"),
    Verdict.WARN: ("⚠", "be careful"),
    Verdict.BLOCK: ("⛔", "don't trust it"),
}
_COLORS = {Verdict.PASS: "\033[32m", Verdict.WARN: "\033[33m", Verdict.BLOCK: "\033[31m"}
_RESET = "\033[0m"


def use_color(*, is_terminal: bool) -> bool:
    """Use ANSI colors only for terminals when NO_COLOR is unset."""
    return is_terminal and "NO_COLOR" not in os.environ


def render_verdict(verdict: Verdict, *, color: bool = False) -> str:
    """Render a verdict with both its symbol and plain-language label."""
    symbol, label = _LABELS[verdict]
    text = f"{symbol} {verdict.value} — {label}"
    return f"{_COLORS[verdict]}{text}{_RESET}" if color else text


def format_sim_time(value: datetime) -> str:
    """Format an instant for display in East Africa Time (UTC+3, no DST)."""
    return value.astimezone(_EAT).strftime("%H:%M:%S EAT")


def configure_utf8_stdout() -> None:
    """Use UTF-8 for CLI text and JSON, including Windows redirected output."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")


def json_line(value: BaseModel | Mapping[str, Any]) -> str:
    """Serialize one structured result as compact JSON on a single line."""
    data = value.model_dump(mode="json") if isinstance(value, BaseModel) else dict(value)
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
