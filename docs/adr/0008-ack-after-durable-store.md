# ADR 0008: Acknowledge only after durable storage

- Status: Accepted for the v0.2 listener/store
- Contract: `ARCHITECTURE.md` §7.10, §7.12

## Context

Acknowledging before data is stored can cause permanent loss if the process stops.

## Decision

The listener sends a positive acknowledgement only after the frame is durably stored; failures receive no acknowledgement or a negative acknowledgement.

## Consequences

Device retries provide at-least-once delivery. Duplicate records remain visible to quality checks.
