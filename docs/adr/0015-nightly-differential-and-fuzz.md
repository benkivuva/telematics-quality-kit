# ADR 0015: Run slow differential and fuzz jobs nightly

- Status: Accepted
- Contract: `ARCHITECTURE.md` §7.13, §11

## Context

Independent-decoder comparisons and extended fuzzing are valuable but can slow every pull request.

## Decision

Run these extended checks nightly while keeping fast deterministic gates on each pull request.

## Consequences

Every change gets fast feedback, with broader independent checks still scheduled regularly.
