# ADR 0011: Use project-specific listener ports

- Status: Accepted for the v0.2 listener
- Contract: `ARCHITECTURE.md` §7.10

## Context

The test listener should run beside Traccar without relying on remembered or conflicting defaults.

## Decision

Use the documented project ports 7001 (Teltonika), 7002 (GT06), and 7003 (Queclink), binding loopback by default.

## Consequences

Both systems can be exercised side by side, and examples remain explicit about network exposure.
