# telematics-quality-kit

**A deterministic, synthetic testbed for telematics data quality.** Generate and decode GT06 and Teltonika device frames, exercise a real parser-in-the-loop ingestion path, inject reversible simulator faults, and inspect every result with an explicit trust verdict.

This is a developer tool for building and testing telematics data systems. It is not a fleet management product, does not connect to real vehicles, and does not issue commands to devices. The current release is **v0.1.4** and uses synthetic data only.

## Contents

- [What you can do](#what-you-can-do)
- [Requirements and install](#requirements-and-install)
- [Configuration](#configuration)
- [60-second walkthrough](#60-second-walkthrough)
- [`eval`](#eval)
- [How quality results work](#how-quality-results-work)
- [Synthetic fleet and protocols](#synthetic-fleet-and-protocols)
- [Command reference](#command-reference)
  - [demo](#demo)
  - [serve: MCP server](#serve-mcp-server)
  - [shell: interactive and scripted sessions](#shell-interactive-and-scripted-sessions)
  - [inject: fault drills against a server](#inject-fault-drills-against-a-server)
  - [stream: pipeline events](#stream-pipeline-events)
  - [init: starter files](#init-starter-files)
  - [doctor: environment check](#doctor-environment-check)
  - [report: static HTML report](#report-static-html-report)
- [MCP tools, resources, and prompts](#mcp-tools-resources-and-prompts)
- [Development and verification](#development-and-verification)
- [Project layout](#project-layout)
- [Determinism, safety, and limitations](#determinism-safety-and-limitations)
- [License](#license)

## What you can do

- Generate deterministic GT06 and Teltonika frames from one seed, then decode them through the same codecs used by the ingestion pipeline.
- Run a synthetic fleet in-process, over MCP stdio, or over Streamable HTTP bound to loopback by default.
- Inspect fleet and vehicle quality through the developer shell or MCP tools.
- Inject reversible faults into the simulator and check that the reported quality changes as expected.
- Follow raw frame, decode, store, check, fault, and verdict events through a bounded event tap.
- Create a self-contained, reproducible HTML report with inline CSS and SVG, no JavaScript, and no external requests.
- Run unit, integration, property, and CLI tests, along with lint, formatting, typing, and dependency-audit checks.

## Requirements and install

- Python **3.12 or newer**
- [`uv`](https://docs.astral.sh/uv/)
- Git, if cloning the repository

Check the active interpreter with `uv run python --version`.

Clone the repository and install the project and its development dependencies:

```bash
git clone https://github.com/benkivuva/telematics-quality-kit.git
cd telematics-quality-kit
uv sync --locked
```

Check the local environment and see the available commands:

```bash
uv run telematics doctor
uv run telematics --help
```

All examples below use `uv run telematics`, which runs the checked-out project in its managed environment. The package also installs `telematics-quality-kit` as an alias for the same CLI. Run `uv run telematics COMMAND --help` for the exact options of any command.

Choose the installation path for how you plan to use the toolkit:

- **Develop from a checkout:** use `uv sync --locked` above; this installs the locked runtime and development dependencies.
- **Run the demo without a checkout:** use `uvx telematics-quality-kit demo` from the published v0.1.4 package.
- **Install into an existing Python environment:** install the published package with `python -m pip install telematics-quality-kit`, then run `telematics demo`.
- **Run an MCP HTTP server in a container:** use Docker Compose as described under [Run the container](#run-the-container).

The no-clone command is:

```bash
uvx telematics-quality-kit demo
```

## Configuration

Drift thresholds are heuristics. The CLI reads these optional environment variables; unset values keep the defaults shown below:

| Variable | Default | Meaning |
| --- | ---: | --- |
| `TELEMATICS_DRIFT_WARN_FRACTION` | `0.01` | Fraction of points that may be flagged before drift becomes WARN. |
| `TELEMATICS_DRIFT_BLOCK_FRACTION` | `0.05` | Fraction of points that may be flagged before drift becomes BLOCK; must be greater than the WARN fraction. |
| `TELEMATICS_DRIFT_STATIONARY_JITTER_METERS` | `25` | Stationary movement tolerance in meters. |

These configured defaults are checked by `uv run pytest tests/unit/test_config.py`.

Set these in the environment before starting `demo`, `serve`, `shell`, `stream`, or `report`. For example, in PowerShell:

```powershell
$env:TELEMATICS_DRIFT_WARN_FRACTION = "0.02"
$env:TELEMATICS_DRIFT_BLOCK_FRACTION = "0.08"
uv run telematics shell
```

The same variables can be exported in Bash. Values must be finite numbers, the BLOCK fraction must exceed WARN, and the jitter threshold must be positive.

## 60-second walkthrough

Watch the [short terminal recording](docs/demo.cast) with an asciinema-compatible
player. The same result can be produced locally with the command below.

Run the deterministic demo:

```bash
uv run telematics demo
```

Three prompts to try with an MCP client:

1. “Give me a health briefing of the fleet. Which vehicles can I trust right now?”
2. “Simulate a rural blackout on TRK-0001, then tell me where that vehicle is.”
3. “Show last week's trips for LRY-0003 and tell me what you could not verify.”

Open the embedded shell and inspect the simulated fleet:

```bash
uv run telematics shell
```

At the `telematics>` prompt, try:

```text
fleet
ls --limit 5
get TRK-0001
report TRK-0001 --verbose
explain TRK-0001 freshness
```

The shell starts with an embedded synthetic fleet. Begin with `help` or `fleet`; `help` lists every command available in the current v0.1 shell.

Exercise a fault and advance simulated time without waiting on the wall clock:

```text
inject blackout TRK-0001 --duration 20m
advance 6m
get TRK-0001
clear
exit
```

Generate a shareable report in the current directory:

```bash
uv run telematics report --out fleet-report.html
```

The report uses deterministic simulated time. Repeating the same command with the same project version and inputs produces the same report bytes.

## How quality results work

Each vehicle receives six checks. Their thresholds are configurable heuristics; they are not ground truth or a replacement for domain-specific validation.

| Check | What it evaluates |
| --- | --- |
| `freshness` | Age of the latest report relative to the profile's expected reporting interval. |
| `drift` | Implausible movement, such as a jump exceeding the profile's maximum speed or excessive stationary jitter. |
| `duplicates` | Repeated telemetry records and excessive heartbeat rates. |
| `ignition` | Excessive or implausible ignition transitions. |
| `plausibility` | Invalid coordinates, future timestamps, clock skew, and profile-inconsistent speeds. |
| `fuel` | Fuel-level changes that cannot be explained by distance and operating context. It flags an unexplained change; it does not claim theft. |

The v0.1 vehicle trust score is the weighted mean of check scores, capped by the worst check verdict:

| Check | Weight |
| --- | ---: |
| Freshness | 0.30 |
| Drift | 0.25 |
| Duplicates | 0.15 |
| Ignition | 0.10 |
| Plausibility | 0.15 |
| Fuel | 0.05 |

The verdict caps are `PASS = 1.0`, `WARN = 0.79`, and `BLOCK = 0.39`. The fleet score is the mean of vehicle scores; the accompanying verdict counts keep a high fleet average from hiding individual problems.

The score weights and caps are asserted by `uv run pytest tests/unit/test_scoring.py`.

| Verdict | Trust label | Meaning |
| --- | --- | --- |
| `PASS` âœ“ | **trust it** | Values are usable for decisions under the configured heuristics. |
| `WARN` âš  | **be careful** | Values are returned with caveats. |
| `BLOCK` â›” | **don't trust it** | A BLOCK is a normal result, not a tool error. Last-known location values may still be present and clearly labelled, but `usable_for_decision` is `false`; affected derived values are withheld and listed. |

Every quality-bearing result includes a `data_quality` object with a plain-language label, symbol, verdict, score, `usable_for_decision`, caveats, withheld values, and the evaluation window. Detailed per-check metrics are available in verbose quality reports. Verdicts are always conveyed using text and a symbol, not color alone.

## Synthetic fleet and protocols

The simulator generates only synthetic identifiers such as `TRK-0001`; its IMEIs are synthetic and zero-prefixed. The default fleet size is 12, the default seed is 42, and supported fleet sizes are 1 through 10,000. That maximum is a validation guard, not a throughput claim. The implemented wire codecs are GT06 and standard Teltonika Codec 8 (`0x08`); Codec 8 Extended (`0x8E`) is not implemented.

The default profile mix is `trk=40,lry=30,car=30`. Profiles are allocated deterministically by largest remainder. Protocol assignment and profile defaults are:

| Profile | Vehicle type | Maximum speed | Reporting interval | Protocol |
| --- | --- | ---: | ---: | --- |
| `trk` | Long-haul truck | 90 km/h | 30 s | Teltonika Codec 8 |
| `lry` | Delivery lorry | 60 km/h | 60 s | Teltonika Codec 8 |
| `car` | Ride-hail / PSV car | 70 km/h | 20 s | GT06 |
| `pik` | Mixed pickup | 80 km/h | 45 s | GT06 |

Fleet bounds, seed behavior, profile assignments, speeds, and report intervals are covered by `uv run pytest tests/unit/test_simulator.py tests/unit/test_profiles.py tests/cli/test_demo.py`.

Set a specific mix with comma-separated percentages that sum to 100:

```bash
uv run telematics serve --vehicles 100 --profile-mix trk=40,lry=30,car=15,pik=15
uv run telematics report --vehicles 40 --profile-mix trk=50,lry=25,car=15,pik=10 --out mixed.html
```

The simulator derives its per-vehicle and per-tick pseudo-random state from the master seed. The same seed, clock, fleet options, and inputs produce the same generated wire bytes and results. Time-sensitive behavior uses an injected simulator clock, not the current wall clock.

## Command reference

The installed command is `telematics`. Its current v0.1 subcommands are:

```text
demo  serve  shell  inject  stream  init  doctor  report  eval
```

Use `uv run telematics --help` or `uv run telematics COMMAND --help` for up-to-date usage. The architecture document also describes future v0.2 commands; they are not part of the current CLI.

The installed package version is `0.1.4`; read it with `uv run python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])"`.

### `eval`

Run the deterministic stale-device, GPS-drift, and rural-blackout contract checks
without a network connection or API key:

```bash
uv run telematics eval
```

The optional model layer compares the same fixed synthetic scenarios with the
quality block on and off. It uses Gemini and writes dated model evidence to
`docs/eval-results.md`; set `GEMINI_API_KEY` or `GOOGLE_API_KEY` before opting in:

```bash
uv run telematics eval --model gemini-1.5-flash --date YYYY-MM-DD
```

To generate the API-key-free evidence page, supply the date of that run:

```bash
uv run telematics eval --date YYYY-MM-DD --out docs/eval-results.md
```

The fixed seed defaults to `42`. To select another seed or output path, use
`--seed` and `--out`. The deterministic layer is part of CI; the model layer is
a manual step and is never run by CI.

### `demo`

Print a deterministic before-and-after fleet table for the vertical-slice quality demo:

```bash
uv run telematics demo
uv run telematics demo --vehicles 20 --seed 7
```

Options:

- `--vehicles N`: fleet size from 1 to 10,000; default `3` for the demo.
- `--seed S`: deterministic integer seed; default `42`.

### `serve`: MCP server

Start an in-memory synthetic fleet and expose the MCP surface. The default transport is Streamable HTTP at `http://127.0.0.1:8000/mcp`:

```bash
uv run telematics serve
```

Options:

- `--vehicles N`: fleet size, default `12`.
- `--seed S`: seed, default `42`.
- `--profile-mix trk=40,lry=30,car=15,pik=15`: profile percentages; values must be positive and sum to 100. Omit a profile to exclude it.
- `--transport streamable-http|stdio`: transport, default `streamable-http`.
- `--host HOST`: HTTP bind host, default `127.0.0.1` (loopback).
- `--port PORT`: HTTP port, default `8000`, valid range 1â€“65,535.
- `--speed Nx`: simulated clock rate, default `1x`. For example, `60x` advances roughly an hour of simulated time per minute of elapsed time.

Examples:

```bash
uv run telematics serve --vehicles 50 --seed 23 --profile-mix trk=40,lry=30,car=15,pik=15
uv run telematics serve --transport streamable-http --host 127.0.0.1 --port 8010 --speed 60x
uv run telematics serve --transport stdio
```

The HTTP server is local-only by default. Use `--host` to change the bind address deliberately; avoid exposing a simulator with destructive fault tools to an untrusted network. The stdio transport reserves stdout for MCP protocol messages.

### `shell`: interactive and scripted sessions

Start an embedded simulator shell (no server required):

```bash
uv run telematics shell
uv run telematics shell --vehicles 200 --seed 42
uv run telematics shell --profile-mix trk=50,lry=20,car=20,pik=10
```

Run one command non-interactively with `-c`:

```bash
uv run telematics shell -c 'fleet'
uv run telematics shell -c 'get TRK-0001'
```

Attach the shell to a running Streamable HTTP MCP server instead of creating an embedded fleet:

```bash
uv run telematics shell --attach
uv run telematics shell --attach http://127.0.0.1:8010/mcp -c 'tools'
```

Available shell commands:

| Command | Behavior |
| --- | --- |
| `fleet` | Show vehicle count, fleet trust score, and PASS/WARN/BLOCK counts. |
| `ls [--limit N]` | List vehicles, lower trust scores first; default limit 50. |
| `get VEHICLE_ID` | Show the last location, age, trust signal, and caveats. |
| `report [VEHICLE_ID] [--verbose]` | Print a structured quality report for a vehicle or the fleet. `--verbose` includes check metrics. |
| `explain VEHICLE_ID CHECK` | Show a check's verdict, score, and metrics. Checks: `freshness`, `drift`, `duplicates`, `ignition`, `plausibility`, `fuel`. |
| `inject FAULT VEHICLE_ID [--severity low\|medium\|high] [--duration 15m]` | Inject a reversible fault into an embedded simulator. |
| `clear` | Clear simulator faults and restore seeded frames. |
| `faults` | List active fault IDs in embedded mode. |
| `advance DURATION` | Advance embedded simulated time by a duration such as `30s`, `6m`, or `1h`. |
| `pause` / `resume` | Pause or resume automatic simulator time in embedded mode. Explicit `advance` still works while paused. |
| `speed [Nx]` | Show or set the automatic simulator clock rate, such as `speed 10x`. |
| `reset` | Clear active simulator faults and restore the seeded frames. |
| `seed INTEGER` | Rebuild the embedded fleet using a new seed. |
| `call TOOL [JSON_ARGUMENTS]` | Call a public MCP tool and print its structured response. |
| `tools` | List tools exposed by the active MCP server. |
| `expect verdict VEHICLE_ID PASS\|WARN\|BLOCK` | Assert a vehicle verdict in a script or interactive session. |
| `expect field VEHICLE_ID PATH VALUE` | Assert a field in the location response, using dotted paths such as `data_quality.usable_for_decision`; `true` and `false` are parsed as booleans. |
| `exit`, `quit`, `Ctrl-D` | Leave the shell. |

Fault names accept aliases: `stale`, `drift`, `blackout`, `dupes`, `flicker`, `skew`, `fuel-spike`, and `burst`; canonical names are also accepted. Severity scales the fault's default magnitude or duration: low `0.5x`, medium `1.0x`, high `2.0x`.

`advance`, `pause`, `resume`, `speed`, `reset`, and `seed` are available only for embedded sessions. An attached session talks only to the server's public MCP tools. The `events` shell command is planned for v0.2 and is not available in v0.1. Tab completion depends on platform readline support and is not available on every Windows Python installation.

Script files are plain text, one shell command per line; blank lines and `#` comments are ignored. Any command error or failed `expect` stops the script with exit code 1:

```bash
uv run telematics init script blackout-drill.tqs
```

Edit the file to contain, for example:

```text
inject blackout TRK-0001 --duration 20m
advance 6m
expect verdict TRK-0001 BLOCK
expect field TRK-0001 data_quality.usable_for_decision false
```

Then run it:

```bash
uv run telematics shell --script blackout-drill.tqs
```

The shell script runs against a new embedded fleet by default. Attach scripts with `--attach URL` only if their commands should use a running MCP server; `advance` will not work in attached mode.

### `inject`: fault drills against a server

The standalone `inject` command calls the simulator-only MCP fault tools on a running server. In one terminal, start the server:

```bash
uv run telematics serve --speed 60x
```

In another terminal, inject a fault:

```bash
uv run telematics inject blackout --vehicle TRK-0001 --severity high --duration 20m
```

Wait for a selected verdict and use the exit code in automation:

```bash
uv run telematics inject blackout --vehicle TRK-0001 --duration 20m --wait 30s --expect BLOCK
# Bash / macOS / Linux / WSL:
echo $?
# PowerShell:
$LASTEXITCODE
```

Options:

- Positional `fault`: canonical names or aliases: `stale_device`/`stale`, `gps_drift`/`drift`, `rural_blackout`/`blackout`, `duplicate_heartbeats`/`dupes`, `ignition_flicker`/`flicker`, `clock_skew`/`skew`, `fuel_sensor_spike`/`fuel-spike`, `buffered_burst`/`burst`.
- `--vehicle ID`: required synthetic vehicle ID.
- `--severity low|medium|high`: default `medium`; scales default magnitude/duration by 0.5x, 1x, or 2x.
- `--duration 15m`: optional simulated fault duration. Supported units are integer seconds (`30s`), minutes (`15m`), and hours (`1h`).
- `--url URL`: MCP endpoint, default `http://127.0.0.1:8000/mcp`.
- `--wait [DURATION]`: poll for a verdict after injection; omitting the duration means `30s`.
- `--expect PASS|WARN|BLOCK`: expected verdict while waiting; default `BLOCK`.

Exit code is 0 if the injection succeeds or the requested verdict is observed, 1 if the wait expires without observing it, 2 for invalid command input, and 3 if the server cannot be reached or does not expose the simulator fault capability. `serve --speed 60x` lets simulated freshness age faster while `inject --wait` uses real elapsed time for its polling timeout. The default vehicle fleet includes `TRK-0001`; IDs depend on selected profile mix and fleet size.

### `stream`: pipeline events

Stream follows the event tap of an embedded fleet. It is intentionally a continuous command; press `Ctrl-C` to stop. Each subscriber uses a bounded queue so stream consumers do not block frame ingestion; older queued events may be dropped when a consumer falls behind.

```bash
uv run telematics stream
uv run telematics stream --vehicles 50 --rate 20
uv run telematics stream --vehicle TRK-0001 --stage issue --stage verdict
uv run telematics stream --issues-only
uv run telematics stream --stage rx --hex
uv run telematics stream --json | jq .
```

Options:

- `--vehicles N`: fleet size, default `12`.
- `--seed S`: deterministic seed, default `42`.
- `--vehicle ID`: follow one vehicle.
- `--stage STAGE`: filter by one or more stages: `rx`, `decode`, `store`, `check`, `issue`, `parse`, `verdict`, or `fault`.
- `--issues-only`: retain priority issues, parse failures, fault events, and verdict changes.
- `--hex`: show full frame hex instead of the short default preview.
- `--json`: emit one schema-validated JSON object per line (summary goes to stderr).
- `--rate N`: maximum normal event output rate in lines per second, default `20`; must be a positive integer. Priority events bypass sampling.

### `init`: starter files

Print a starter template to the terminal or create a new file. Existing paths are never overwritten:

```bash
uv run telematics init fleet
uv run telematics init fleet fleet.yaml
uv run telematics init scenario blackout.yaml
uv run telematics init script drill.tqs
```

Templates:

- `fleet`: seed, vehicle count, and `profile_mix` percentages.
- `scenario`: name, seed, vehicle count, duration, optional profile mix, and a list of fault/vehicle/severity entries.
- `script`: commands for `telematics shell --script`.

Scenario files are YAML and are loaded with PyYAML `safe_load`. Example:

```yaml
name: blackout-drill
seed: 42
vehicles: 12
duration: 1h
profile_mix:
  trk: 40
  lry: 30
  car: 20
  pik: 10
faults:
  - fault: rural_blackout
    vehicle_id: TRK-0001
    severity: high
```

### `doctor`: environment check

Check for Python 3.12+, `uv`, and an installed project package:

```bash
uv run telematics doctor
```

The command prints one status or repair hint per check and returns non-zero if a requirement is missing.

### `report`: static HTML report

Generate one self-contained synthetic fleet report without starting a server:

```bash
uv run telematics report
uv run telematics report --clean --out clean.html
uv run telematics report --scenario blackout.yaml --out blackout-report.html
uv run telematics report --inject drift:CAR-0001:high --duration 1h --fault-duration 20m --open
```

With no `--clean`, `--scenario`, or `--inject`, the default is a labelled **showcase** scenario with faults applied to sample vehicles. Use `--clean` for a baseline, `--inject` for explicit faults, or `--scenario` for a YAML scenario. A scenario can be combined with additional `--inject` flags; `--clean` cannot be combined with `--inject`.

Options:

- `--vehicles N`: number of synthetic vehicles; defaults to 12 or the scenario's `vehicles` value.
- `--seed S`: seed; defaults to 42 or the scenario's seed.
- `--scenario FILE`: YAML scenario file.
- `--clean`: produce a fault-free baseline.
- `--inject FAULT:VEHICLE[:SEVERITY]`: add a fault; repeat the option for multiple faults. Severity defaults to `medium`. Example: `--inject blackout:TRK-0001:high`.
- `--duration 1h`: total simulated report window; defaults to 1 hour or the scenario's duration.
- `--fault-duration 20m`: how long faults are active at the end of the window; default `20m`.
- `--detail N`: number of worst vehicles to include in detailed cards, from 1 to 200; default `50`.
- `--profile-mix trk=40,lry=30,car=20,pik=10`: profile distribution; defaults to scenario mix if supplied.
- `--out FILE`: output path; default `fleet-report.html`.
- `--open`: open the resulting file in the default browser.

The report writes to `--out` and silently replaces an existing file at that path. Choose a new path or back up the existing report if you need to keep it. The report includes a synthetic-data notice, scenario and seed, simulated range in East Africa Time, injected faults, fleet score and verdict counts, a worst-first vehicle table, per-check metrics and caveats for detailed vehicles, freshness timelines, and local SVG tracks. A BLOCKed vehicle's location track is withheld when the quality rules prohibit presenting it as decision-ready. HTML strings are escaped. The document contains inline CSS and SVG, a restrictive CSP meta tag, no JavaScript, no external fonts or requests, and a black-and-white-friendly print stylesheet. Reports larger than 5 MB produce a warning suggesting a lower `--detail` value.

The report size warning and deterministic output checks are exercised by `uv run pytest tests/cli/test_report.py`.

## MCP tools, resources, and prompts

`telematics serve` exposes 11 v0.1 tools over either stdio or Streamable HTTP. `inject_fault` and `reset_simulator` are registered only when the active backend exposes the simulator fault capability; they are not general device-control commands. The tool count and schemas are checked by `uv run pytest tests/integration/test_mcp_surface.py`.

| Tool | Purpose |
| --- | --- |
| `list_vehicles` | Paginated vehicle list with compact quality signals. |
| `get_vehicle_location` | Last location, age, and quality. |
| `get_trip_history` | Trip history for a vehicle and time window; affected distance may be withheld. |
| `get_fuel_events` | Unexplained fuel changes for a vehicle or fleet and window. |
| `get_quality_report` | Vehicle or fleet quality report; optional `verbose` includes check metrics. |
| `check_fleet_freshness` | Fleet report age and freshness verdicts. |
| `check_gps_drift` | GPS drift results for one vehicle and time window. |
| `check_duplicates` | Repeated records and heartbeat-rate checks for a time window. |
| `list_quality_issues` | Ranked WARN/BLOCK findings and suggested follow-up tools. |
| `inject_fault` | Simulator-only reversible fault injection. |
| `reset_simulator` | Simulator-only reset to seeded frames. |

Every output has a `schema_version`; input and output models reject undeclared fields. JSON Schema files for each tool are in [`docs/schemas/`](docs/schemas/). `BLOCK` responses are successful tool responses with `usable_for_decision=false`, not JSON-RPC errors.

The server also exposes:

- Resources: `quality://checks` and `fleet://profiles`.
- Prompts: `fleet_health_briefing`, `investigate_vehicle`, and `fault_drill`.

For an MCP client supporting stdio, configure its server entry with the command below and replace the directory with your checkout's absolute path. A stdio client launches `telematics serve` as a child process, so there is no second terminal to start and keep open. `stdout` is reserved for MCP protocol messages; diagnostics go to `stderr`.

```json
{
  "mcpServers": {
    "telematics-quality-kit": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/telematics-quality-kit",
        "telematics",
        "serve",
        "--transport",
        "stdio"
      ]
    }
  }
}
```

On Windows, use an absolute path and JSON-escape each backslash (or use forward slashes), for example:

```json
{
  "mcpServers": {
    "telematics-quality-kit": {
      "command": "uv",
      "args": ["run", "--directory", "C:/Users/you/projects/telematics-quality-kit", "telematics", "serve", "--transport", "stdio"]
    }
  }
}
```

For an HTTP-capable client, open two terminals. Keep the server running in the first:

```bash
uv run telematics serve
```

Configure/connect the client in the second terminal or its settings to `http://127.0.0.1:8000/mcp`. Stop the server with `Ctrl-C` when finished. HTTP clients do not launch the server process for you.

## Development and verification

Numeric defaults and limits shown in this README have executable checks:

| Values | Verification command |
| --- | --- |
| Drift defaults | `uv run pytest tests/unit/test_config.py` |
| Quality weights and verdict caps | `uv run pytest tests/unit/test_scoring.py` |
| Fleet bounds, seeds, profiles, speeds, and report intervals | `uv run pytest tests/unit/test_simulator.py tests/unit/test_profiles.py tests/cli/test_demo.py` |
| CLI option bounds, exit codes, stream rates, and report size limit | `uv run pytest tests/cli` |
| MCP tool count and output schemas | `uv run pytest tests/integration/test_mcp_surface.py` |
| Package version | `uv run python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])"` |

The short walkthrough recording is generated from `uv run telematics demo`; it is
stored as [`docs/demo.cast`](docs/demo.cast).

### Run the container

The published GHCR image runs the Streamable HTTP MCP server. Docker Compose pulls the prebuilt image and publishes it on host loopback only:

```bash
docker compose up -d
```

Connect an MCP client to `http://127.0.0.1:8000/mcp`. Stop the service with `docker compose down`. The image runs as a non-root user with a read-only root filesystem and dropped capabilities. See [the threat model](docs/threat-model.md) and [privacy notes](docs/privacy.md).

The container filesystem is read-only and Compose does not mount a persistent report directory by default. To create a report inside its temporary `/tmp` filesystem and copy it to the host (PowerShell example):

```powershell
docker compose run --name tqk-report --no-deps telematics-quality-kit report --out /tmp/report.html
docker cp tqk-report:/tmp/report.html .\report.html
docker rm tqk-report
```

The report disappears with the temporary container unless copied out. A bind mount can also be used, but the host directory must be writable by the container's non-root user; on Windows, Docker Desktop handles the file sharing while Linux hosts may need to adjust directory ownership or permissions.

Install all project and development dependencies:

```bash
uv sync
```

Run all local quality gates:

```bash
make verify
```

`make verify` runs Ruff lint, Ruff format check, strict mypy for `src/telematics`, and the full pytest suite. Additional useful commands:

```bash
# All test tiers
uv run pytest

# Individual test tiers
uv run pytest -m unit
uv run pytest -m integration
uv run pytest -m property

# CLI tests
uv run pytest tests/cli

# Lint, formatting, typing
uv run ruff check .
uv run ruff format --check .
uv run mypy src/telematics

# Dependency vulnerability audit
make security
# equivalent
uv run pip-audit

# Deterministic demo
make demo
# equivalent
uv run telematics demo
```

GitHub Actions runs lint, format, typing, the full test suite, and CLI smoke tests on Linux, macOS, and Windows. The security workflow runs repository and dependency scanning. Protocol fixture sources and independent CRC verification notes are documented in [`tests/fixtures/README.md`](tests/fixtures/README.md).

Useful project references:
- [`docs/schemas/`](docs/schemas/): generated MCP tool schemas.

## Project layout

```text
src/telematics/
  backends/    FleetBackend and simulator implementation
  cli/         demo, serve, shell, inject, stream, init, doctor, report commands
  codecs/      GT06, Teltonika Codec 8, and CRC implementations
  ingest/      framing, parser-in-the-loop pipeline, and bounded event tap
  mcp/         strict schemas, server tools, resources, and prompts
  models/      telemetry and quality result models
  quality/     six pure quality checks and weighted scoring
  report/      deterministic report data, HTML rendering, and SVG generation
  service/     backend-independent application logic
  simulator/   deterministic generator, Kenya profiles, and real-time clock driver
  store/       bounded in-memory telemetry store
tests/
  cli/         command-line and report behavior
  fixtures/    copied protocol vectors and provenance
  integration/ in-process MCP and serve behavior
  property/    parser, scoring, and determinism invariants
  unit/        focused codec, pipeline, simulator, and quality tests
```

## Determinism, safety, and limitations

- **Synthetic only:** example IDs, frames, and locations are generated test data, not captured device data or production fleet information.
- **No device commands:** the toolkit does not issue commands to GPS trackers or vehicles. Fault injection mutates the local simulator only.
- **Loopback default:** the HTTP server binds to `127.0.0.1` unless `--host` is explicitly changed.
- **Parser in the data path:** simulator frames are encoded to protocol bytes and decoded before telemetry reaches storage and quality checks.
- **Deterministic time and randomness:** fixed seeds and injected clocks make simulations, tests, and reports repeatable. The long-running `stream` command sleeps to drive a live display; tests do not rely on wall-clock sleeps.
- **Bounded event consumers:** event tap subscriptions have bounded queues; slow consumers do not block the ingestion pipeline and can miss older queued events.
- **Heuristic checks:** scores and thresholds describe configurable defaults. They are not a guarantee that a value is correct.
- **v0.1 scope:** current commands are listed in the [command reference](#command-reference). Features marked v0.2 in `ARCHITECTURE.md`â€”including a TCP listener, real Traccar backend, capture/replay, dashboard, metrics intervals, and external device simulatorâ€”are not available in this release.

## License

This project is distributed under the [Apache-2.0 License](LICENSE).
