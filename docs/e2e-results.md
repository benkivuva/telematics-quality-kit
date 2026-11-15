# End-to-end QA results — v0.1.4 release gate

Date: 2026-11-15
Branch: `feat/phase7-evidence-harness`
Base commit: `047a2a4` (plus this pass's uncommitted fixes)
Environment: WSL Ubuntu, Python 3.12, `uv`, loopback-only MCP server

## Result

```
PASS: 348 checks passed, 0 failed
```

The suite is `./e2e_test.sh` in the repository root. It reports each failing
check with its recent output, continues through the remaining checks, and exits
non-zero if any check fails. It also fails any check whose output contains a
Python traceback.

Full test and lint results after the fixes:

```
uv run pytest -q
266 passed in 51.78s

uv run ruff check .
All checks passed!

uv run ruff format --check .
137 files already formatted

uv run mypy src/telematics
Success: no issues found in 52 source files
```

## What the suite covers

### Cleanup

- Deleted the temporary root scripts `test_everything.tqs` and `test_ux.sh`.
- The suite asserts both paths are absent.

### CLI help surface

Every subcommand and every flag shown by `--help` is exercised:

| Command | Flags covered |
| --- | --- |
| `demo` | `--vehicles`, `--seed` |
| `serve` | `--vehicles`, `--seed`, `--profile-mix`, `--transport` (stdio and streamable-http), `--host`, `--port`, `--speed` |
| `shell` | `--vehicles`, `--seed`, `--profile-mix`, `--attach` (default URL and explicit URL), `-c`, `--script` |
| `inject` | `--vehicle`, `--severity`, `--duration`, `--url`, `--wait`, `--expect` |
| `stream` | `--vehicles`, `--seed`, `--vehicle`, `--stage`, `--issues-only`, `--hex`, `--json`, `--rate` |
| `init` | `fleet`, `scenario`, `script`, optional path |
| `doctor` | `--help` and the live environment check |
| `report` | `--vehicles`, `--seed`, `--scenario`, `--clean`, `--inject`, `--duration`, `--fault-duration`, `--detail`, `--profile-mix`, `--out`, `--open` |
| `eval` | `--seed`, `--model`, `--out`, `--date`, `--manual` |

### Init templates

- `init fleet`, `init scenario`, and `init script` print deterministic
  templates to stdout.
- `init fleet PATH` writes the file.
- A second write to the same path is refused with status `2`.
- An unknown template is rejected with status `2`.
- Without a path, `init` does not create a default file; the suite asserts no
  stray file appears.

### Interactive shell

A real heredoc session (`shell --vehicles 6 --seed 42 <<'COMMANDS'`) runs the
full command set and asserts the printed text:

`fleet`, `ls --limit`, `ls --worse-than`, `get`, `report`, `explain`,
`inject` (including an alias), `clear`, `faults`, `advance`, `pause`,
`resume`, `speed`, `reset`, `seed`, `call`, `tools`, `expect`, `exit`.

Additional scripted-session checks cover:

- `-c` single-command mode and `--script` drill mode.
- A passing script and a failing script that stops on the failing line.
- `-c` and `--script` mutual exclusion.
- A missing script file.
- `--attach` with no server (clean connection error) and the default URL.
- `--profile-mix trk=100` producing only TRK vehicles.
- `--vehicles` and `--seed` being respected.

### MCP over Streamable HTTP

A loopback server is started with:

```
telematics serve --vehicles 20 --seed 9 --profile-mix trk=50,lry=50 \
  --transport streamable-http --host 127.0.0.1 --port <free-port> --speed 60x
```

The suite then verifies:

- `shell --attach <url> -c fleet` sees 20 healthy vehicles.
- `tools` lists the full v0.1 surface, including `inject_fault` and
  `get_quality_report`.
- `get` returns a vehicle location.
- `inject` over the attached shell works.
- `clear` over the attached shell works.
- Embedded-only commands (`advance`, `pause`, `resume`, `speed`, `reset`,
  `seed`, `faults`) fail with the documented "only in embedded mode" message.
- `inject --wait 15s --expect BLOCK` observes the expected `BLOCK` verdict.
- `--duration` and fault aliases work.
- An unreachable server returns status `3` with the `uv run telematics serve`
  hint.
- The server log contains no traceback, and the process group is terminated on
  exit.

The stdio transport is also checked: `serve --transport stdio` exits cleanly
on EOF with status `0`.

### Static report

- Every report input flag is exercised in one run, plus `--clean`,
  `--scenario`, and `--open`.
- `--open` is run with `BROWSER=/bin/true`, so no real browser is launched.
- Reports are byte-identical for the same seed and options.
- The default output path works (`fleet-report.html` in the current directory).
- Generated HTML contains:
  - A `Content-Security-Policy` meta tag with `default-src 'none'`.
  - No `<script>` tag.
  - No `http://` or `https://` URL.
  - No `src=`, `href=`, `@import`, or CSS `url()`.
- A scenario name of `<script>alert(1)</script>` is rendered escaped and does
  not produce a script tag.

### Evaluation

- Deterministic eval: 3 scenarios, 18/18 assertions, all pass.
- `--date` + `--out` writes Markdown evidence with the date and seed.
- `--manual` with `y/n/y` answers reports `2/3 rubric passes` and the
  question-set SHA-256.
- `--out` without `--date` is rejected.
- `--manual` with `--out` is rejected.
- A malformed date is rejected.
- `--model` without an API key returns status `2` with the documented message.
- `--model` without `--date` is rejected before any model call.

### Edge cases and boundaries

| Case | Expected and observed |
| --- | --- |
| Unknown subcommand | status `2`, choices listed |
| No subcommand | status `2` |
| `demo --vehicles 0` / `10001` | status `2` |
| `demo --seed nope` | status `2` |
| `stream --vehicles 0` / `10001` | status `2` |
| `stream --rate -5` / `0` | status `2` |
| `stream --rate fast` | status `2` |
| `stream --stage bogus` | status `2` |
| `serve --port 0` / `--speed 0` | status `2` |
| `serve --transport udp` | status `2` |
| `report --vehicles 0`, `--detail 0/201`, `--duration 0m`, `--fault-duration 0m` | status `2` |
| `report --profile-mix` below 100 | status `2` |
| `report --clean --inject ...` | status `2` |
| `report --inject broken` | status `2` |
| `report --inject stale:FAKE-9999` | status `2` |
| `report --scenario missing.yaml` | status `2` |
| `report --out /nonexistent-dir/...` | status `4` |
| `ls --limit 0` / `999` | status `1`, usage text |
| `ls --limit` without a value | status `1` |
| `ls --worse-than BROKEN` | status `1`, verdict choices |
| `ls --bogus` | status `1` |
| `get` with no/too many arguments | status `1` |
| `get FAKE-9999` | status `1`, no `INFO`, no traceback |
| `report` with two vehicles or an unknown option | status `1` |
| `report FAKE-9999` | status `1` |
| `explain` with one argument or unknown check | status `1` |
| `call` with no tool, malformed JSON, an array, or an unknown tool | status `1` |
| `inject` missing positionals, bad fault, bad vehicle, bad severity, bad duration, unknown option | status `1`, clean usage text |
| `clear TRK-0001 rural_blackout` | status `1`, `unknown fault`, no Pydantic text |
| `clear all FAKE-9999` | status `1`, `unknown vehicle` |
| `clear` with too many arguments | status `1` |
| `advance 5`, `advance 0m`, `advance 2x`, bare `advance` | status `1` |
| `speed 0`, `speed fast` | status `1` |
| `seed abc` | status `1` |
| `expect` bad syntax or wrong verdict | status `1` |
| Empty filtered result (`ls --worse-than BLOCK` on a clean fleet) | zero rows |

### Large fleet and fault isolation

At 600 vehicles the suite asserts:

- Baseline: `PASS 600 WARN 0 BLOCK 0`.
- After injecting `gps_drift` on `TRK-0001` and advancing 2 minutes:
  `PASS 599 WARN 0 BLOCK 1`.
- `ls --worse-than WARN` prints exactly one row, the blocked vehicle.

This is the regression guard for the earlier fleet-wide injection cascade.

## Defects found and fixed during this pass

The first full run had one failing check: the suite incorrectly expected
`init fleet` without a path to write `fleet.yaml`, but the CLI deliberately
prints the template to stdout in that case. The check was corrected to assert
the documented print-and-do-not-write behavior. Two real UX defects were found
before the clean run and fixed:

1. **Shell `inject` leaked Pydantic validation errors.**
   `inject nonsense TRK-0001` sent the bad fault to the MCP server and printed
   an `InjectFaultInput` `literal_error`. `do_inject` now validates the fault,
   vehicle, severity, duration, and options before calling the server, matching
   the `clear` command's existing validation.

2. **CLI `inject` accepted malformed values until after a network round-trip.**
   `telematics inject gps_drift --vehicle TRK-0001 --duration 0m` was parsed as
   a string and only rejected by the server (or hidden behind a connection
   error when no server was running). The fault and duration are now validated
   by argparse, so the command exits `2` with a usage error before connecting.

Fixes and regression tests:

- `src/telematics/cli/shell.py` — local `inject` validation.
- `src/telematics/cli/main.py` — `_inject_fault` and `_inject_duration`
  argparse validators.
- `src/telematics/cli/inject.py` — `canonical_fault()` shared alias/fault
  validator.
- `tests/cli/test_shell.py` — unknown fault, unknown vehicle, invalid severity.
- `tests/cli/test_inject.py` — parametrized argparse rejection for unknown
  fault, zero duration, and malformed duration.

The previously fixed issues remain covered by the suite:

- `ls --worse-than` filters before `--limit` and paginates the whole fleet.
- One injected fault produces exactly one `BLOCK`.
- `clear` validates its arguments and explains that history may remain.
- MCP `INFO` logs are suppressed in CLI sessions.
- `clear all` prints the history warning only when faults were cleared.

## Reproduce

```bash
./e2e_test.sh
```

Requires bash, coreutils `timeout`, `setsid`, `python3`, and `uv`. The suite
binds an ephemeral loopback port only; it never uses `0.0.0.0`.

## Not verified in this pass

- `make security` (gitleaks, semgrep, pip-audit, trivy) was not run.
- The successful `eval --model` path was not run because no API key was
  available.
- A real browser was not launched for `report --open`; `BROWSER=/bin/true` was
  used to verify the code path and file output.
- `stream` was exercised for several seconds and interrupted with `SIGINT`; it
  was not left running indefinitely.
- Docker and `docker-compose.yml` were not exercised.
- A real Claude Desktop or other external MCP client was not exercised; the
  attached-session tests use the CLI's own Streamable HTTP client.
