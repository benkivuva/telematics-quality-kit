# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.4] - Unreleased

### Added

- Deterministic Phase 7 evidence harness: `telematics eval` checks the stale-device,
  GPS-drift, and rural-blackout scenarios without an API key or network access.
- Optional human-graded `eval --manual` rubric. `--manual` can now be combined with
  `--date` and `--out` to save the raw prompts, `y`/`n` answers, and final score.
- Optional Gemini model layer (`eval --model`), opt-in and API-key gated.
- Repository end-to-end QA script `e2e_test.sh`, run in CI on `ubuntu-latest`.
- Per-package coverage gates for `codecs`, `quality`, `service`, and `mcp`.

### Changed

- README documents `ls --worse-than`, `eval --manual`, and the difference between
  `clear` (keeps historical points) and `reset` (wipes simulator history).
- `serve --transport streamable-http` binds to loopback `127.0.0.1` by default.
- Releases are gated on tests and locked dependencies.

### Fixed

- README no longer contains double-encoded UTF-8 (mojibake) in verdict and range text.
- `AttachedSession.call_tool` no longer reports client-side `TypeError` or `ValueError`
  as a connection failure; only transport errors are reported as connectivity problems.
- CLI and shell fault injection validate faults and durations before contacting a server.
- `pyproject.toml` is read reliably after stripping a byte-order mark.

## [0.1.3] - 2026-11-11

### Changed

- Include `README.md` in the PyPI package metadata.
- Bump the package version to `0.1.3`.

## [0.1.2] - 2026-11-11

### Fixed

- Strip the byte-order mark from `pyproject.toml` so build and audit tools read it.

### Changed

- Update version references and pin the cosign installer by commit SHA.
- Bump the package version to `0.1.2`.

## [0.1.1] - 2026-11-10

### Fixed

- Repair the release pipeline for `v0.1.1`.
- Bump the cosign installer and pin it by commit SHA.

### Changed

- Bump the package version to `0.1.1`.

## [0.1.0] - 2026-11-10

### Added

- Initial v0.1 release of the deterministic telematics data-quality testbed.
- Hand-encoded GT06 and Teltonika Codec 8 frame generation and decoding, with seeded
  fleet profiles and reversible fault injection.
- Six quality checks with weighted scoring, trust verdicts, plain-language labels,
  caveats, and withheld-value reporting.
- Embedded CLI, MCP tool surface, Streamable HTTP and stdio transports, and a
  self-contained static HTML report with no JavaScript or external requests.
- Developer shell, live `stream` view, `doctor` environment check, and scenario files.
- Security and distribution controls: gitleaks, semgrep, pip-audit, trivy, signed
  release artifacts, and hardened container defaults.
