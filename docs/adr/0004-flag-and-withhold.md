# ADR 0004: Flag quality failures and withhold affected values

- Status: Accepted
- Contract: `ARCHITECTURE.md` §8.2–§8.3

## Context

Silently dropping questionable telemetry hides evidence; returning derived values without qualification invites false confidence.

## Decision

Every result carries a trust signal. A BLOCK is a normal result, marks data unusable for decisions, and withholds affected derived values.

## Consequences

Callers can inspect the original result and its caveats while being told exactly which derived values are unavailable.
