# ADR 0013: Keep the dashboard offline and build-free

- Status: Accepted for the v0.2 dashboard
- Contract: `ARCHITECTURE.md` §7.16

## Context

A local dashboard should not need a JavaScript build chain or contact third-party hosts.

## Decision

Serve local assets without a build step, external requests, or remote map tiles.

## Consequences

The dashboard has fewer runtime dependencies and remains usable offline; tracks use local SVG.
