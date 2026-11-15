# ADR 0014: Require vendor vectors before Queclink code

- Status: Accepted
- Contract: `ARCHITECTURE.md` §7.14

## Context

Queclink message formats vary by device series and incomplete recollection is not a protocol specification.

## Decision

Do not implement Queclink until a chosen series has confirmed manual details and copied golden examples with provenance.

## Consequences

The project avoids guessed wire behavior and can test against independently sourced vectors.
