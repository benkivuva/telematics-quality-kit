# ADR 0002: Streamable HTTP and stdio

- Status: Accepted
- Contract: `ARCHITECTURE.md` §5, §7.5

## Context

MCP clients need both a child-process connection and a local HTTP connection.

## Decision

Support Streamable HTTP and stdio through the MCP SDK. Do not add legacy SSE or FastAPI.

## Consequences

The SDK remains the only protocol server dependency. stdio reserves stdout for protocol messages and sends logs to stderr.
