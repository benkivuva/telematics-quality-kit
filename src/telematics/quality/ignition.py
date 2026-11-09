"""Pure ignition chatter evaluation with debounce."""

from collections.abc import Sequence

from telematics.config import IgnitionConfig
from telematics.models.quality import CheckResult, Verdict
from telematics.models.telemetry import TelemetryPoint
from telematics.quality._common import result


class IgnitionCheck:
    """Detect repeated ignition transitions inside short windows."""

    def __init__(self, config: IgnitionConfig) -> None:
        self._config = config

    def evaluate(self, points: Sequence[TelemetryPoint]) -> CheckResult:
        ordered = sorted(
            (point for point in points if point.ignition_on is not None),
            key=lambda point: point.device_time,
        )
        transitions: list[float] = []
        previous: TelemetryPoint | None = None
        for point in ordered:
            if previous is not None and point.ignition_on != previous.ignition_on:
                elapsed = (point.device_time - previous.device_time).total_seconds()
                if elapsed >= self._config.debounce_seconds:
                    transitions.append(point.device_time.timestamp())
            previous = point
        episodes = 0
        cursor = 0
        while cursor < len(transitions):
            end = cursor
            while (
                end < len(transitions)
                and transitions[end] - transitions[cursor] <= self._config.window_seconds
            ):
                end += 1
            if end - cursor > self._config.max_transitions:
                episodes += 1
                cursor = end
            else:
                cursor += 1
        verdict = Verdict.BLOCK if episodes >= 3 else Verdict.WARN if episodes else Verdict.PASS
        return result("ignition", verdict, transitions=len(transitions), episodes=episodes)
