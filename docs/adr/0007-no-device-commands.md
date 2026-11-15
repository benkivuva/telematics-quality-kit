# ADR 0007: Never send commands to devices

- Status: Accepted
- Contract: `ARCHITECTURE.md` §1, §7.10, §19

## Context

Device command channels can disable or reconfigure operational equipment.

## Decision

The toolkit never sends commands to devices. A listener may send only protocol acknowledgements.

## Consequences

The product remains a read-only testbed and cannot become a remote-control path through an MCP tool.
