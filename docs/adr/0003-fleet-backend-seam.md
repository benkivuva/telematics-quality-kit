# ADR 0003: One FleetBackend seam

- Status: Accepted
- Contract: `ARCHITECTURE.md` §7.4

## Context

Simulator and future data sources need to feed the same service and quality logic.

## Decision

Use one `FleetBackend` interface as the service layer's data source and swap point.

## Consequences

The service layer stays independent of MCP and I/O. Backend-specific capabilities remain explicit.
