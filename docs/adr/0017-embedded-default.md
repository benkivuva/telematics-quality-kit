# ADR 0017: Embedded mode is the default

- Status: Accepted
- Contract: `ARCHITECTURE.md` §7.7

## Context

The first-use experience should work without a running server or account.

## Decision

Use an embedded, seeded simulator by default for `demo`, `shell`, and `stream`.

## Consequences

The default path is zero-config and deterministic; attached behavior is explicit.
