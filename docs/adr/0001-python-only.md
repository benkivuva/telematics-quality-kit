# ADR 0001: Python only

- Status: Accepted
- Contract: `ARCHITECTURE.md` §5, §16

## Context

The toolkit needs one implementation language for its codecs, simulator, MCP server, and CLI.

## Decision

Implement the v0.1 toolkit in Python.

## Consequences

One toolchain serves runtime code and tests. Protocol behavior remains directly testable through Python's standard testing tools.
