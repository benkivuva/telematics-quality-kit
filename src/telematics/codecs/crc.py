"""Checksums used by supported telematics protocols."""


def crc16_x25(data: bytes) -> int:
    """Return the CRC-16/X25 checksum for *data*."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc >>= 1
    return crc ^ 0xFFFF
