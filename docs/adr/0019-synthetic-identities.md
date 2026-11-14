# ADR 0019: Use unmistakably synthetic identities

- Status: Accepted
- Contract: `ARCHITECTURE.md` §7.2

## Context

Test fixtures and examples must not identify real vehicles or devices.

## Decision

Use synthetic non-plate-like vehicle IDs and zero-prefixed IMEIs reserved by this project.

## Consequences

Generated examples are visibly synthetic and do not collide with real identity formats.
