# ADR 0022: Build the CLI on stdlib `argparse` and `cmd`

- Status: Accepted
- Contract: `ARCHITECTURE.md` §7.7

## Context

The CLI needs scriptable commands and an interactive shell without adding a framework dependency. The shell must also degrade gracefully on Windows, where `readline` is unavailable.

## Decision

Use stdlib `argparse` for commands and stdlib `cmd` for the interactive shell. Do not add a CLI framework.

## Consequences

The dependency surface stays small and the shell works on every supported platform. Windows loses tab completion and history, which the documentation states plainly; `prompt_toolkit` remains an optional future extra, not a requirement.
