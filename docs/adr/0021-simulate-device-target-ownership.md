# ADR 0021: Allow `simulate-device` to target any host, with a rate cap and ownership flag

- Status: Accepted
- Contract: `ARCHITECTURE.md` §7.7

## Context

Developers need to point emulated GT06 and Teltonika devices at their own ingestion servers, which may sit outside loopback or private address ranges. The same traffic generator can be misused as a flooding tool against a server the operator does not control.

## Decision

Accept any `--target`. Cap total frame rate (`--max-rate`, default 100 frames/s), require `--i-own-this-target` for targets outside loopback and private ranges, print the target before sending, and send only device-side protocol frames.

## Consequences

The tool stays useful for testing other people's stacks without becoming a flooding tool. The operator asserts authorization explicitly, and the toolkit still never sends commands to devices.
