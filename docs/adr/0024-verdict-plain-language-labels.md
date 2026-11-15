# ADR 0024: Give every verdict a plain-language label

- Status: Accepted
- Contract: `ARCHITECTURE.md` §8.2–§8.3

## Context

AI assistants and humans must reach the same conclusion from a result. A bare `PASS`, `WARN` or `BLOCK` invites interpretation, and colour alone excludes some readers.

## Decision

Pair every verdict with a fixed label: *trust it* (PASS), *be careful* (WARN), or *don't trust it* (BLOCK). Always show verdicts as text and a symbol, never colour alone, and tell tool descriptions to relay the label.

## Consequences

The same unambiguous wording appears in every result and CLI surface. Results are slightly more verbose, and the labels become part of the public contract rather than presentation detail.
