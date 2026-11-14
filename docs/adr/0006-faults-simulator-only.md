# ADR 0006: Fault tools are simulator-only

- Status: Accepted
- Contract: `ARCHITECTURE.md` §7.5

## Context

Fault injection is useful for testing but must not mutate a real fleet.

## Decision

Register fault tools only when the selected backend exposes the simulator fault capability.

## Consequences

The real-backend path has no fault mutation surface; tests assert capability-based registration.
