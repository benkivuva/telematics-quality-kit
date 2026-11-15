# ADR 0010: Return metrics as intervals

- Status: Accepted
- Contract: `ARCHITECTURE.md` §8.4

## Context

Derived distance, fuel, and emissions depend on incomplete observations and assumptions.

## Decision

Represent derived metrics as intervals with a declared kind, basis, and assumptions.

## Consequences

Callers can distinguish bounded evidence from exact measurements and inspect why an interval has its width.
