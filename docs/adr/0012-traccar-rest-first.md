# ADR 0012: Use Traccar REST before direct database access

- Status: Accepted for the v0.2 Traccar backend
- Contract: `ARCHITECTURE.md` §7.13

## Context

Direct database access couples the toolkit to internal schema and credentials.

## Decision

Use Traccar's read-only REST API first. Direct PostgreSQL access is optional and read-only.

## Consequences

The default integration exposes fewer credentials and is less coupled to Traccar migrations.
