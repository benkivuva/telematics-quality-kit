"""Seeded synthetic GT06 frame generator."""

from telematics.clock import Clock
from telematics.codecs.gt06 import GT06Codec
from telematics.models.telemetry import TelemetryPoint


class Simulator:
    """Generate deterministic, synthetic device frames from an injected clock."""

    def __init__(self, *, seed: int, clock: Clock) -> None:
        self._seed = seed
        self._clock = clock
        self._codec = GT06Codec()

    def frames(self, *, vehicles: int) -> tuple[tuple[str, bytes], ...]:
        """Return one parser-ready frame for each synthetic vehicle."""
        if vehicles < 1:
            raise ValueError("vehicles must be positive")
        result: list[tuple[str, bytes]] = []
        for index in range(1, vehicles + 1):
            vehicle_id = f"TRK-{index:04d}"
            point = TelemetryPoint(
                device_time=self._clock.now(),
                latitude=-1.2921 + (index - 1) * 0.001,
                longitude=36.8219 + (index - 1) * 0.001,
                speed_kph=float(35 + (self._seed + index) % 30),
                course_deg=(self._seed + index * 17) % 360,
                satellites=8,
                serial_number=index,
            )
            result.append((vehicle_id, self._codec.encode((point,))))
        return tuple(result)
