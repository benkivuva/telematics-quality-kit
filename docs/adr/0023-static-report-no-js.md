# ADR 0023: Keep the static report free of JavaScript and external requests

- Status: Accepted
- Contract: `ARCHITECTURE.md` §7.9

## Context

The report must open from disk, survive email and ticket attachments, work offline, and be auditable in one file. Scripts, remote assets and servers all widen the attack surface and add failure modes.

## Decision

Generate one self-contained HTML file with inline CSS and SVG, no `<script>`, no `<link>`, and no external requests. Add a restrictive Content-Security-Policy meta tag, escape every dynamic string, and make output byte-identical for the same seed and options.

## Consequences

The report opens anywhere and can be reviewed without running code. It has no interactive sorting or paging, so large fleets are bounded by `--detail` instead. Reproducibility is a testable property rather than a convention.
