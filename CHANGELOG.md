## [0.1.4] - 2026-11-16

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

### Known Limitations

- The optional model-layer eval (Phase 7 gate) requires a user-supplied `GEMINI_API_KEY` or `GOOGLE_API_KEY` and is not run in CI. The deterministic eval layer (18/18 assertions) runs in CI and passes successfully. Therefore, this release ships with **the deterministic layer only; the model gate remains open**.