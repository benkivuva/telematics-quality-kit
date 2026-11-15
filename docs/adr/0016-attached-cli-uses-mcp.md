# ADR 0016: Attached CLI commands use MCP

- Status: Accepted
- Contract: `ARCHITECTURE.md` §7.7

## Context

Maintaining a separate attached-command path risks behavior that differs from what an AI client sees.

## Decision

Attached CLI operations call the public MCP tools.

## Consequences

The CLI and MCP surface share one contract and exercise the same validation and output models.
