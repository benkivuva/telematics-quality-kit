"""Incremental framing for GT06 and Teltonika TCP byte streams."""

_GT06_START = b"\x78\x78"
_GT06_STOP = b"\x0d\x0a"
_TELTONIKA_PREAMBLE = b"\x00\x00\x00\x00"


class GT06FrameSplitter:
    """Buffer and emit complete short-header GT06 frames."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> tuple[bytes, ...]:
        """Consume arbitrary stream bytes and return all complete frames."""
        self._buffer.extend(chunk)
        frames: list[bytes] = []
        while True:
            start = self._buffer.find(_GT06_START)
            if start < 0:
                del self._buffer[: max(0, len(self._buffer) - 1)]
                break
            if start:
                del self._buffer[:start]
            if len(self._buffer) < 3:
                break
            declared_length = self._buffer[2]
            total_length = declared_length + 5
            if declared_length < 3:
                del self._buffer[0]
                continue
            if len(self._buffer) < total_length:
                break
            if self._buffer[total_length - 2 : total_length] != _GT06_STOP:
                del self._buffer[0]
                continue
            frames.append(bytes(self._buffer[:total_length]))
            del self._buffer[:total_length]
        return tuple(frames)


class TeltonikaFrameSplitter:
    """Buffer Teltonika frames whose length spans Codec ID through record count."""

    def __init__(self, *, max_frame_size: int = 1292) -> None:
        if max_frame_size < 16:
            raise ValueError("maximum frame size is too small for Teltonika framing")
        self._max_frame_size = max_frame_size
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> tuple[bytes, ...]:
        """Consume arbitrary stream bytes and resynchronize after garbage."""
        self._buffer.extend(chunk)
        frames: list[bytes] = []
        while True:
            start = self._buffer.find(_TELTONIKA_PREAMBLE)
            if start < 0:
                # Preserve at most the three trailing bytes that can prefix a preamble.
                del self._buffer[: max(0, len(self._buffer) - 3)]
                break
            if start:
                del self._buffer[:start]
            if len(self._buffer) < 8:
                break
            data_length = int.from_bytes(self._buffer[4:8], "big")
            frame_length = 8 + data_length + 4
            if data_length < 2 or frame_length > self._max_frame_size:
                del self._buffer[0]
                continue
            if len(self._buffer) < frame_length:
                break
            frames.append(bytes(self._buffer[:frame_length]))
            del self._buffer[:frame_length]
        return tuple(frames)
