# ADR 0025: Derive the fleet verdict from the worst vehicle

- Status: Accepted
- Contract: `ARCHITECTURE.md` §8.2

## Context

A fleet trust score is an average, so a healthy majority can produce a reassuring number while one vehicle is blocked. Reporting only counts leaves the fleet headline ambiguous, and a caller may act on the average instead of the vehicle that must not be used.

## Decision

Make the fleet verdict the worst vehicle verdict (D1): any BLOCK vehicle makes the fleet BLOCK, with `usable_for_decision = false`. Surface the affected vehicle IDs and withheld values in bounded form, and keep the fleet trust score as the mean, reported with PASS/WARN/BLOCK counts and never as a substitute for the verdict.

## Consequences

One blocked vehicle blocks the fleet-level answer, which is the honest result. Consumers must inspect per-vehicle detail before using fleet data, and fleet outputs stay bounded by summarising the worst vehicles instead of enumerating every row.
