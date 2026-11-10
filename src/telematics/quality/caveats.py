"""Plain-language caveats an AI assistant can relay."""

from collections.abc import Callable, Mapping

from telematics.models.quality import CheckResult, Verdict

_CaveatWriter = Callable[[CheckResult], str]


def caveat_for(check: CheckResult) -> str | None:
    """Return one plain sentence for a non-PASS check, or None for PASS."""
    if check.verdict is Verdict.PASS:
        return None
    writer = _WRITERS.get(check.name)
    if writer is None:
        return None
    return writer(check)


def _metric(check: CheckResult, name: str, default: float) -> float:
    value = check.metric.get(name, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _age_text(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    hours = minutes // 60
    return f"{hours} hour{'s' if hours != 1 else ''}"


def _freshness(check: CheckResult) -> str:
    age_text = _age_text(int(_metric(check, "age_seconds", 0)))
    if check.verdict is Verdict.BLOCK:
        return f"Location is {age_text} old; do not present it as current."
    return f"Location is {age_text} old; treat it as a recent but not live position."


def _drift(check: CheckResult) -> str:
    percent = round(_metric(check, "flagged_fraction", 0.0) * 100)
    if check.verdict is Verdict.BLOCK:
        return (
            f"Position is jumping implausibly between fixes; {percent}% of recent points "
            "look wrong, so treat this location as unreliable."
        )
    return (
        f"Position shows some implausible jumps; {percent}% of recent points look wrong, "
        "so double-check this location."
    )


def _duplicates(check: CheckResult) -> str:
    percent = round(_metric(check, "duplicate_fraction", 0.0) * 100)
    if check.verdict is Verdict.BLOCK:
        return (
            f"{percent}% of recent records are duplicates; counts and distances may be "
            "overstated, so do not trust totals."
        )
    return (
        f"{percent}% of recent records are duplicates; counts and distances may be "
        "slightly overstated."
    )


def _ignition(check: CheckResult) -> str:
    transitions = int(_metric(check, "transitions", 0))
    if check.verdict is Verdict.BLOCK:
        return (
            f"Ignition switched {transitions} times in short windows; ignition state is "
            "unreliable, so do not use it to decide whether the engine is running."
        )
    return f"Ignition switched {transitions} times recently; ignition state may be unreliable."


def _plausibility(check: CheckResult) -> str:
    issues: list[str] = []
    invalid = int(_metric(check, "invalid_points", 0))
    future = int(_metric(check, "future_points", 0))
    excessive = int(_metric(check, "excessive_speed_points", 0))
    skew = int(_metric(check, "max_clock_skew_seconds", 0))
    if invalid:
        issues.append(f"{invalid} invalid position{'s' if invalid != 1 else ''}")
    if future:
        issues.append(f"{future} record{'s' if future != 1 else ''} with future timestamps")
    if excessive:
        issues.append(f"{excessive} record{'s' if excessive != 1 else ''} above the speed limit")
    if skew:
        issues.append(f"device clock {_age_text(skew)} off the server clock")
    detail = "; ".join(issues)
    if check.verdict is Verdict.BLOCK:
        return f"Data is structurally implausible: {detail}, so do not trust it."
    return f"Some data looks implausible: {detail}."


def _fuel(check: CheckResult) -> str:
    drop = _metric(check, "unexplained_drop", 0.0)
    distance = _metric(check, "distance_km", 0.0)
    return (
        f"Fuel level dropped {drop:.0f}% while the vehicle travelled only "
        f"{distance:.1f} km; the fuel reading may be unreliable."
    )


_WRITERS: Mapping[str, _CaveatWriter] = {
    "freshness": _freshness,
    "drift": _drift,
    "duplicates": _duplicates,
    "ignition": _ignition,
    "plausibility": _plausibility,
    "fuel": _fuel,
}
