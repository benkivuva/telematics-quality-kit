# ADR 0009: Do not constrain point uniqueness in storage

- Status: Accepted for the v0.2 store
- Contract: `ARCHITECTURE.md` §7.12

## Context

Retransmitted records are evidence needed by the duplicates check.

## Decision

The point store does not impose a uniqueness constraint that removes duplicate records.

## Consequences

Deduplication remains a quality signal instead of being hidden by persistence behavior.
