# ADR 0005: Parsers stay in the data path

- Status: Accepted
- Contract: `ARCHITECTURE.md` §7.1, §7.3

## Context

Quality checks need the same normalized data a real device frame would produce.

## Decision

Simulator frames are encoded and decoded by the protocol codecs before they reach storage or quality evaluation.

## Consequences

Codec defects surface in end-to-end behavior instead of being bypassed by simulator-only objects.
