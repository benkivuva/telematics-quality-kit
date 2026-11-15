# ADR 0018: Use one bounded event tap

- Status: Accepted
- Contract: `ARCHITECTURE.md` §7.3

## Context

Multiple observers need a consistent view without allowing a slow subscriber to stall ingestion.

## Decision

Publish typed pipeline events through one tap with bounded per-subscriber queues and drop accounting.

## Consequences

Consumers see the same event vocabulary, while slow consumers lose their own oldest events rather than blocking the pipeline.
