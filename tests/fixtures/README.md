# Fixture provenance

## GT06 vectors

The GT06 login and login-ACK vectors are copied from the public GT06 protocol
document example recorded in `ARCHITECTURE.md` §7.1. Their CRC-16/X25 values
were independently checked with a separate bitwise implementation.

## Teltonika Codec 8 vector

`teltonika_codec8.hex` is copied byte-for-byte from the public Codec 8 packet
example recorded in `ARCHITECTURE.md` §7.1. The Teltonika Telematics Wiki
defines Data Field Length as the byte count from Codec ID through the second
record count, and says CRC-16/IBM covers that same range:
[Teltonika Codec wiki](https://wiki.teltonika-gps.com/view/Codec).

For this fixture the full frame is indexed from zero. CRC input is exactly
`frame[8:62]` (54 bytes, starting with `0x08` and ending with the second
record count `0x01`). The following four bytes are the 32-bit CRC field
`00 00 C7 CF`. An independent bitwise CRC-16/IBM calculation over those 54
bytes gives `0xC7CF`; CRC-16/X25 over the same slice gives `0x5DAF`.
