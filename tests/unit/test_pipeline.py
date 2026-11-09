"""Parser-in-the-loop ingest tests."""

from datetime import UTC, datetime

import pytest

from telematics.codecs.gt06 import GT06Codec
from telematics.ingest.pipeline import IngestPipeline
from telematics.models.telemetry import TelemetryPoint
from telematics.store.memory import MemoryPointStore


@pytest.mark.unit
def test_pipeline_decodes_frame_before_storing_point() -> None:
    point = TelemetryPoint(datetime(2024, 4, 5, 6, 7, 8, tzinfo=UTC), 12.5, -45.25, 18, 123, 8, 7)
    store = MemoryPointStore()
    pipeline = IngestPipeline(GT06Codec(), store)

    decoded = pipeline.ingest("TRK-0001", GT06Codec().encode((point,)))

    assert decoded == (point,)
    assert store.latest("TRK-0001") == point
