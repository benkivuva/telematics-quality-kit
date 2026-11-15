# ADR 0020: Control simulated time through an injected clock

- Status: Accepted
- Contract: `ARCHITECTURE.md` §7.3

## Context

Time-dependent behavior should be testable without wall-clock sleeps or nondeterministic reads.

## Decision

Inject a clock into simulation and evaluation; allow embedded sessions to advance it explicitly.

## Consequences

Freshness and recovery behavior is reproducible and can be exercised without waiting.
