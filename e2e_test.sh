#!/usr/bin/env bash
# End-to-end QA suite for the telematics-quality-kit v0.1 CLI.
#
# Covers every subcommand and flag, the interactive shell command set, MCP
# fault injection over Streamable HTTP, malformed inputs, boundary values,
# large fleets, and the static report's security properties.
#
# Run from the repository root: ./e2e_test.sh

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT" || exit 1

TMP="$(mktemp -d "${TMPDIR:-/tmp}/telematics-e2e.XXXXXX")"
OUT="$TMP/output.txt"
TEL=(uv run telematics)
TEL_BIN="$ROOT/.venv/bin/telematics"
SERVER_PID=""
SERVER_READY=0
PORT=""
TOTAL=0
FAILED=0

cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill -TERM -- "-$SERVER_PID" 2>/dev/null || kill -TERM "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -rf "$TMP"
}
trap cleanup EXIT

pass() {
  TOTAL=$((TOTAL + 1))
  printf '  ok   %s\n' "$1"
}

fail() {
  TOTAL=$((TOTAL + 1))
  FAILED=$((FAILED + 1))
  printf '  FAIL %s\n' "$1"
  if [[ -f "$OUT" ]]; then
    tail -n 12 "$OUT" | sed 's/^/       /'
  fi
}

section() {
  printf '\n== %s ==\n' "$1"
}

run() {
  local desc="$1" expected="$2"
  shift 2
  : >"$OUT"
  "$@" >"$OUT" 2>&1
  local status=$?
  if [[ "$status" -ne "$expected" ]]; then
    fail "$desc (exit $status, expected $expected)"
  elif grep -Fq "Traceback (most recent call last)" "$OUT"; then
    fail "$desc (Python traceback)"
  else
    pass "$desc"
  fi
}

run_stdin() {
  local desc="$1" expected="$2" input="$3"
  shift 3
  : >"$OUT"
  "$@" <"$input" >"$OUT" 2>&1
  local status=$?
  if [[ "$status" -ne "$expected" ]]; then
    fail "$desc (exit $status, expected $expected)"
  elif grep -Fq "Traceback (most recent call last)" "$OUT"; then
    fail "$desc (Python traceback)"
  else
    pass "$desc"
  fi
}

run_in() {
  local desc="$1" expected="$2" dir="$3"
  shift 3
  : >"$OUT"
  (cd "$dir" && "$@") >"$OUT" 2>&1
  local status=$?
  if [[ "$status" -ne "$expected" ]]; then
    fail "$desc (exit $status, expected $expected)"
  elif grep -Fq "Traceback (most recent call last)" "$OUT"; then
    fail "$desc (Python traceback)"
  else
    pass "$desc"
  fi
}

run_timeout() {
  local desc="$1" expected="$2" seconds="$3"
  shift 3
  : >"$OUT"
  timeout -s INT "$seconds" "$@" >"$OUT" 2>&1
  local status=$?
  if [[ "$status" -ne "$expected" ]]; then
    fail "$desc (exit $status, expected $expected)"
  elif grep -Fq "Traceback (most recent call last)" "$OUT"; then
    fail "$desc (Python traceback)"
  else
    pass "$desc"
  fi
}

contains() {
  local desc="$1" pattern="$2"
  if grep -Fq -- "$pattern" "$OUT"; then
    pass "$desc"
  else
    fail "$desc (missing: $pattern)"
  fi
}

not_contains() {
  local desc="$1" pattern="$2"
  if grep -Fq -- "$pattern" "$OUT"; then
    fail "$desc (unexpected: $pattern)"
  else
    pass "$desc"
  fi
}

matches() {
  local desc="$1" pattern="$2"
  if grep -Eq -- "$pattern" "$OUT"; then
    pass "$desc"
  else
    fail "$desc (no match: $pattern)"
  fi
}

line_count_equals() {
  local desc="$1" expected="$2" actual
  actual="$(grep -c . "$OUT" || true)"
  if [[ "$actual" -eq "$expected" ]]; then
    pass "$desc"
  else
    fail "$desc (lines: $actual, expected $expected)"
  fi
}

matching_line_count_equals() {
  local desc="$1" pattern="$2" expected="$3" actual
  actual="$(grep -Ec -- "$pattern" "$OUT" || true)"
  if [[ "$actual" -eq "$expected" ]]; then
    pass "$desc"
  else
    fail "$desc (matching lines: $actual, expected $expected)"
  fi
}

contains_in() {
  local desc="$1" file="$2" pattern="$3"
  if grep -Fq -- "$pattern" "$file"; then
    pass "$desc"
  else
    fail "$desc (missing in $(basename "$file"): $pattern)"
  fi
}

not_contains_in() {
  local desc="$1" file="$2" pattern="$3"
  if grep -Fq -- "$pattern" "$file"; then
    fail "$desc (unexpected in $(basename "$file"): $pattern)"
  else
    pass "$desc"
  fi
}

validate_json_lines() {
  local desc="$1" file="$2"
  if python3 - "$file" <<'PY'
import json
import sys

path = sys.argv[1]
count = 0
for number, line in enumerate(open(path, encoding="utf-8"), start=1):
    line = line.strip()
    if not line or not line.startswith("{"):
        continue
    try:
        json.loads(line)
    except json.JSONDecodeError as exc:
        print(f"line {number}: {exc}: {line[:160]}")
        raise SystemExit(1) from exc
    count += 1
if count == 0:
    raise SystemExit(f"no JSON lines found in {path}")
print(f"validated {count} JSON line(s)")
PY
  then
    pass "$desc"
  else
    fail "$desc (invalid JSON output)"
  fi
}

start_server() {
  PORT="$(python3 - <<'PY'
import socket

with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
)"
  setsid "${TEL[@]}" serve \
    --vehicles 20 \
    --seed 9 \
    --profile-mix trk=50,lry=50 \
    --transport streamable-http \
    --host 127.0.0.1 \
    --port "$PORT" \
    --speed 60x \
    >"$TMP/serve.log" 2>&1 &
  SERVER_PID=$!
  local attempt
  for attempt in $(seq 1 100); do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
      return 1
    fi
    if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then
      exec 3>&-
      SERVER_READY=1
      return 0
    fi
    sleep 0.25
  done
  return 1
}

printf 'telematics-quality-kit end-to-end QA\n'
printf 'repository: %s\n' "$ROOT"
printf 'temp dir:   %s\n' "$TMP"

# ---------------------------------------------------------------------------
section "Cleanup"
# ---------------------------------------------------------------------------
if [[ ! -e "$ROOT/test_everything.tqs" && ! -e "$ROOT/test_ux.sh" ]]; then
  pass "temporary stress scripts are gone"
else
  fail "temporary stress scripts still exist in the repository root"
fi

# ---------------------------------------------------------------------------
section "Help surface"
# ---------------------------------------------------------------------------
run "top-level --help" 0 "${TEL[@]}" --help
contains "top-level help lists every subcommand" "{demo,serve,shell,inject,stream,init,doctor,report,eval}"

run "demo --help" 0 "${TEL[@]}" demo --help
contains "demo help lists --vehicles" "--vehicles"
contains "demo help lists --seed" "--seed"

run "serve --help" 0 "${TEL[@]}" serve --help
contains "serve help lists --vehicles" "--vehicles"
contains "serve help lists --seed" "--seed"
contains "serve help lists --profile-mix" "--profile-mix"
contains "serve help lists --transport" "--transport"
contains "serve help lists --host" "--host"
contains "serve help lists --port" "--port"
contains "serve help lists --speed" "--speed"

run "shell --help" 0 "${TEL[@]}" shell --help
contains "shell help lists --vehicles" "--vehicles"
contains "shell help lists --seed" "--seed"
contains "shell help lists --profile-mix" "--profile-mix"
contains "shell help lists --attach" "--attach"
contains "shell help lists -c" "-c SHELL_COMMAND"
contains "shell help lists --script" "--script"

run "inject --help" 0 "${TEL[@]}" inject --help
contains "inject help lists --vehicle" "--vehicle"
contains "inject help lists --severity" "--severity"
contains "inject help lists --duration" "--duration"
contains "inject help lists --url" "--url"
contains "inject help lists --wait" "--wait"
contains "inject help lists --expect" "--expect"

run "stream --help" 0 "${TEL[@]}" stream --help
contains "stream help lists --vehicles" "--vehicles"
contains "stream help lists --seed" "--seed"
contains "stream help lists --vehicle" "--vehicle"
contains "stream help lists --stage" "--stage"
contains "stream help lists --issues-only" "--issues-only"
contains "stream help lists --hex" "--hex"
contains "stream help lists --json" "--json"
contains "stream help lists --rate" "--rate"

run "init --help" 0 "${TEL[@]}" init --help
contains "init help lists fleet" "fleet"
contains "init help lists scenario" "scenario"
contains "init help lists script" "script"

run "doctor --help" 0 "${TEL[@]}" doctor --help
contains "doctor help shows usage" "usage: telematics doctor"

run "report --help" 0 "${TEL[@]}" report --help
contains "report help lists --vehicles" "--vehicles"
contains "report help lists --seed" "--seed"
contains "report help lists --scenario" "--scenario"
contains "report help lists --clean" "--clean"
contains "report help lists --inject" "--inject"
contains "report help lists --duration" "--duration"
contains "report help lists --fault-duration" "--fault-duration"
contains "report help lists --detail" "--detail"
contains "report help lists --profile-mix" "--profile-mix"
contains "report help lists --out" "--out"
contains "report help lists --open" "--open"

run "eval --help" 0 "${TEL[@]}" eval --help
contains "eval help lists --seed" "--seed"
contains "eval help lists --model" "--model"
contains "eval help lists --out" "--out"
contains "eval help lists --date" "--date"
contains "eval help lists --manual" "--manual"

# ---------------------------------------------------------------------------
section "Doctor"
# ---------------------------------------------------------------------------
run "doctor environment check" 0 "${TEL[@]}" doctor
contains "doctor reports Python" "OK Python"
contains "doctor reports uv" "OK uv available"
contains "doctor reports the installed package" "OK package installed"

# ---------------------------------------------------------------------------
section "Demo"
# ---------------------------------------------------------------------------
run "demo runs with --vehicles and --seed" 0 "${TEL[@]}" demo --vehicles 5 --seed 7
contains "demo prints the baseline heading" "telematics demo - baseline"
contains "demo prints the stale-device section" "after stale-device fault"
line_count_equals "demo prints no unexpected rows" 14

run "demo --vehicles 1 boundary" 0 "${TEL[@]}" demo --vehicles 1 --seed 42
contains "single-vehicle demo shows the stale WARN" "WARN"

run "demo is deterministic for one seed" 0 "${TEL[@]}" demo --vehicles 4 --seed 99
cp "$OUT" "$TMP/demo-a.txt"
run "demo deterministic rerun" 0 "${TEL[@]}" demo --vehicles 4 --seed 99
if diff -q "$TMP/demo-a.txt" "$OUT" >/dev/null; then
  pass "demo output is byte-identical for the same seed"
else
  fail "demo output changed for the same seed"
fi

run "demo rejects --vehicles 0" 2 "${TEL[@]}" demo --vehicles 0
run "demo rejects --vehicles 10001" 2 "${TEL[@]}" demo --vehicles 10001
run "demo rejects a non-integer seed" 2 "${TEL[@]}" demo --seed nope
run "demo rejects an unknown flag" 2 "${TEL[@]}" demo --profile-mix trk=100

# ---------------------------------------------------------------------------
section "Init"
# ---------------------------------------------------------------------------
run "init fleet prints a template" 0 "${TEL[@]}" init fleet
contains "fleet template contains a seed" "seed: 42"
contains "fleet template contains a profile mix" "profile_mix:"

run "init scenario prints a template" 0 "${TEL[@]}" init scenario
contains "scenario template contains a duration" "duration: 1h"
contains "scenario template contains a fault" "- fault: rural_blackout"

run "init script prints a template" 0 "${TEL[@]}" init script
contains "script template contains fleet" "fleet"
contains "script template contains expect" "expect verdict"

run "init fleet writes a path" 0 "${TEL[@]}" init fleet "$TMP/written-fleet.yaml"
[[ -f "$TMP/written-fleet.yaml" ]] && pass "init wrote the fleet file" || fail "init did not write the fleet file"
run "init refuses to overwrite" 2 "${TEL[@]}" init fleet "$TMP/written-fleet.yaml"
contains "overwrite refusal is explained" "refusing to overwrite"

mkdir -p "$TMP/init-default"
run_in "init without a path prints instead of writing" 0 "$TMP/init-default" "$TEL_BIN" init fleet
contains "printed template contains a profile mix" "profile_mix:"
if [[ ! -e "$TMP/init-default/fleet.yaml" ]]; then
  pass "init without a path leaves no stray file"
else
  fail "init without a path wrote an unexpected file"
fi

run "init rejects an unknown template" 2 "${TEL[@]}" init nope
run "init requires a template" 2 "${TEL[@]}" init

# ---------------------------------------------------------------------------
section "Shell: interactive session"
# ---------------------------------------------------------------------------
cat >"$TMP/interactive.txt" <<'COMMANDS'
fleet
ls --limit 3
get TRK-0001
explain TRK-0001 freshness
inject drift TRK-0001 --severity high --duration 10m
faults
advance 2m
fleet
ls --worse-than WARN
clear all
fleet
faults
reset
fleet
pause
resume
speed 10x
speed
seed 99
fleet
expect verdict TRK-0001 PASS
exit
COMMANDS
run_stdin "interactive shell session via heredoc" 0 "$TMP/interactive.txt" \
  "${TEL[@]}" shell --vehicles 6 --seed 42
contains "shell prints its intro" "Synthetic fleet ready"
contains "fleet prints the fleet summary" "6 vehicles · fleet trust 1.00 · PASS 6 WARN 0 BLOCK 0"
contains "ls --limit prints a vehicle row" "CAR-0001     ✓ PASS — trust it 1.00"
contains "get prints location and usability" "usable_for_decision=True"
contains "explain prints check metrics" "freshness PASS · score 1.00"
contains "inject canonicalises the drift alias" "gps_drift on TRK-0001 (high)"
contains "inject prints the expected impact" "expected:"
contains "faults lists the active fault" "gps_drift TRK-0001 (high)"
contains "advance reports simulated time" "sim time"
contains "fleet reflects the injected BLOCK" "PASS 5 WARN 0 BLOCK 1"
contains "ls --worse-than WARN keeps only the blocked vehicle" "TRK-0001     ⛔ BLOCK — don't trust it"
contains "clear explains that history may remain" \
  "Note: cleared active faults, but historical bad points remain. Use 'reset' to wipe the simulator history."
contains "fleet recovers after clear" "PASS 6 WARN 0 BLOCK 0"
contains "faults reports an empty list" "no active faults"
contains "reset reports its run" "simulator reset; cleared 0 faults"
contains "pause reports paused state" "simulator paused"
contains "resume reports resumed state" "simulator resumed"
contains "speed sets a multiplier" "simulator speed 10x"
contains "seed reseeds the simulator" "simulator reseeded with seed 99"
contains "expect passes for a healthy vehicle" "expectation passed: PASS"

# ---------------------------------------------------------------------------
section "Shell: command arguments and filters"
# ---------------------------------------------------------------------------
run "ls --limit bounds the page" 0 "${TEL[@]}" shell --vehicles 6 --seed 42 -c 'ls --limit 3'
line_count_equals "ls --limit 3 prints exactly three rows" 3

run "ls --limit 200 is accepted" 0 "${TEL[@]}" shell --vehicles 6 --seed 42 -c 'ls --limit 200'
line_count_equals "ls --limit 200 prints the whole fleet" 6

run "ls --worse-than BLOCK on a clean fleet is empty" 0 "${TEL[@]}" shell --vehicles 6 --seed 42 -c 'ls --worse-than BLOCK'
line_count_equals "empty filter prints no rows" 0

cat >"$TMP/filter.tqs" <<'TQS'
inject gps_drift TRK-0001 --severity high
advance 2m
ls --worse-than WARN --limit 1
TQS
run "ls filter is applied before --limit" 0 "${TEL[@]}" shell --vehicles 6 --seed 42 --script "$TMP/filter.tqs"
matching_line_count_equals "filter returns one blocked vehicle" "⛔ BLOCK" 1
contains "filtered row is the blocked vehicle" "TRK-0001     ⛔ BLOCK"
not_contains "filtered output hides PASS rows" "✓ PASS — trust it"

run "ls rejects --limit 999" 1 "${TEL[@]}" shell --vehicles 6 -c 'ls --limit 999'
contains "ls --limit 999 explains the bound" "--limit must be between 1 and 200"

run "ls rejects --limit 0" 1 "${TEL[@]}" shell --vehicles 6 -c 'ls --limit 0'
run "ls rejects --worse-than BROKEN" 1 "${TEL[@]}" shell --vehicles 6 -c 'ls --worse-than BROKEN'
contains "ls explains the verdict choices" "--worse-than must be PASS, WARN, or BLOCK"
run "ls rejects an unknown option" 1 "${TEL[@]}" shell --vehicles 6 -c 'ls --bogus'
run "ls rejects a missing option value" 1 "${TEL[@]}" shell --vehicles 6 -c 'ls --limit'

run "get requires one vehicle" 1 "${TEL[@]}" shell --vehicles 6 -c 'get'
run "get rejects two vehicles" 1 "${TEL[@]}" shell --vehicles 6 -c 'get TRK-0001 TRK-0002'
run "get rejects an unknown vehicle cleanly" 1 "${TEL[@]}" shell --vehicles 6 -c 'get FAKE-9999'
contains "unknown vehicle is an error" "error:"
not_contains "unknown vehicle leaks no INFO log" "INFO"
not_contains "unknown vehicle leaks no traceback" "Traceback"

run "report emits JSON for one vehicle" 0 "${TEL[@]}" shell --vehicles 6 -c 'report TRK-0001 --verbose'
validate_json_lines "report --verbose output is valid JSON" "$OUT"
contains "verbose report contains checks" '"checks"'

run "report rejects an unknown option" 1 "${TEL[@]}" shell --vehicles 6 -c 'report --bogus'
run "report rejects two vehicle arguments" 1 "${TEL[@]}" shell --vehicles 6 -c 'report TRK-0001 TRK-0002'
run "report unknown vehicle is clean" 1 "${TEL[@]}" shell --vehicles 6 -c 'report FAKE-9999'

run "explain requires two arguments" 1 "${TEL[@]}" shell --vehicles 6 -c 'explain TRK-0001'
run "explain rejects an unknown check" 1 "${TEL[@]}" shell --vehicles 6 -c 'explain TRK-0001 nope'
contains "unknown check is named" "unknown check: nope"

run "call requires a tool name" 1 "${TEL[@]}" shell --vehicles 6 -c 'call'
run "call rejects malformed JSON" 1 "${TEL[@]}" shell --vehicles 6 -c 'call get_quality_report {bad}'
contains "malformed JSON is explained" "invalid JSON arguments"
run "call rejects a JSON array" 1 "${TEL[@]}" shell --vehicles 6 -c 'call get_quality_report []'
contains "array arguments are rejected" "tool arguments must be a JSON object"
run "call rejects an unknown tool" 1 "${TEL[@]}" shell --vehicles 6 -c 'call not_a_tool {}'
not_contains "unknown tool leaks no traceback" "Traceback"

run "call returns structured JSON" 0 "${TEL[@]}" shell --vehicles 6 -c 'call get_quality_report {"verbose": false}'
validate_json_lines "call output is valid JSON" "$OUT"
contains "call output carries schema_version" '"schema_version"'

run "tools lists the v0.1 surface" 0 "${TEL[@]}" shell --vehicles 1 -c 'tools'
line_count_equals "tools lists eleven tools" 11
contains "tools lists list_vehicles" "list_vehicles"
contains "tools lists inject_fault" "inject_fault"
contains "tools lists reset_simulator" "reset_simulator"

run "inject requires two positionals" 1 "${TEL[@]}" shell --vehicles 6 -c 'inject gps_drift'
run "inject rejects an unknown fault without a pydantic error" 1 "${TEL[@]}" shell --vehicles 6 -c 'inject nonsense TRK-0001'
contains "unknown fault is named" "unknown fault: nonsense"
not_contains "unknown fault leaks no pydantic text" "validation error"
run "inject rejects an unknown vehicle" 1 "${TEL[@]}" shell --vehicles 6 -c 'inject gps_drift FAKE-9999'
contains "unknown injection vehicle is named" "unknown vehicle: FAKE-9999"
run "inject rejects an invalid severity" 1 "${TEL[@]}" shell --vehicles 6 -c 'inject gps_drift TRK-0001 --severity bogus'
contains "invalid severity is explained" "severity must be low, medium, or high"
run "inject rejects a malformed duration" 1 "${TEL[@]}" shell --vehicles 6 -c 'inject gps_drift TRK-0001 --duration 5'
run "inject rejects an unknown option" 1 "${TEL[@]}" shell --vehicles 6 -c 'inject gps_drift TRK-0001 --bogus'

run "clear rejects a vehicle in the fault position" 1 "${TEL[@]}" shell --vehicles 6 -c 'clear TRK-0001 rural_blackout'
contains "clear names the bad fault" "unknown fault: TRK-0001"
not_contains "clear leaks no pydantic text" "validation error"
run "clear rejects an unknown vehicle" 1 "${TEL[@]}" shell --vehicles 6 -c 'clear all FAKE-9999'
contains "clear names the unknown vehicle" "unknown vehicle: FAKE-9999"
run "clear rejects too many arguments" 1 "${TEL[@]}" shell --vehicles 6 -c 'clear all TRK-0001 extra'
run "clear with no active faults is quiet" 0 "${TEL[@]}" shell --vehicles 6 -c 'clear all'
contains "clear reports zero cleared faults" "cleared 0 simulator faults"
not_contains "clear warns only when faults were cleared" "historical bad points remain"

run "advance rejects a bare number" 1 "${TEL[@]}" shell --vehicles 6 -c 'advance 5'
run "advance rejects zero" 1 "${TEL[@]}" shell --vehicles 6 -c 'advance 0m'
run "advance rejects a bad unit" 1 "${TEL[@]}" shell --vehicles 6 -c 'advance 2x'
run "advance requires an argument" 1 "${TEL[@]}" shell --vehicles 6 -c 'advance'

run "speed rejects zero" 1 "${TEL[@]}" shell --vehicles 6 -c 'speed 0'
run "speed rejects text" 1 "${TEL[@]}" shell --vehicles 6 -c 'speed fast'
run "seed rejects text" 1 "${TEL[@]}" shell --vehicles 6 -c 'seed abc'

run "expect rejects bad syntax" 1 "${TEL[@]}" shell --vehicles 6 -c 'expect'
run "expect fails on a wrong verdict" 1 "${TEL[@]}" shell --vehicles 6 -c 'expect verdict TRK-0001 BLOCK'
contains "expect explains the mismatch" "expectation failed"
run "expect passes a field predicate" 0 "${TEL[@]}" shell --vehicles 6 -c \
  'expect field TRK-0001 data_quality.usable_for_decision true'
contains "field expectation passes" "expectation passed: True"

run "unknown shell command fails" 1 "${TEL[@]}" shell --vehicles 6 -c 'bogus'
contains "unknown command is named" "unknown command: bogus"

# ---------------------------------------------------------------------------
section "Shell: modes, seeds, and scripts"
# ---------------------------------------------------------------------------
run "shell --vehicles and --seed" 0 "${TEL[@]}" shell --vehicles 4 --seed 7 -c 'fleet'
contains "shell respects the fleet size" "4 vehicles"
run "shell --profile-mix assigns profiles" 0 "${TEL[@]}" shell --vehicles 2 --seed 7 --profile-mix trk=100 -c 'ls --limit 2'
matches "profile mix starts with TRK-0001" '^TRK-0001'
matches "profile mix starts with TRK-0002" '^TRK-0002'
not_contains "profile mix excludes CAR vehicles" "CAR-"

run "shell -c and --script are mutually exclusive" 2 "${TEL[@]}" shell -c fleet --script "$TMP/nope.tqs"
run "shell reports a missing script" 4 "${TEL[@]}" shell --script "$TMP/no-such.tqs"
contains "missing script is explained" "cannot read script"

cat >"$TMP/pass.tqs" <<'TQS'
fleet
expect verdict TRK-0001 PASS
TQS
run "shell --script passes a valid drill" 0 "${TEL[@]}" shell --vehicles 3 --seed 42 --script "$TMP/pass.tqs"
contains "script prints its expectation" "expectation passed: PASS"

cat >"$TMP/fail.tqs" <<'TQS'
fleet
expect verdict TRK-0001 BLOCK
fleet
TQS
run "shell --script stops on a failed expectation" 1 "${TEL[@]}" shell --vehicles 3 --seed 42 --script "$TMP/fail.tqs"
contains "script reports the failing line" "line 2 failed"

printf 'exit\n' >"$TMP/exit.txt"
run_stdin "shell --attach defaults to the documented URL and exits" 0 "$TMP/exit.txt" \
  "${TEL[@]}" shell --attach
contains "attached shell prints its intro" "Synthetic fleet ready"

run "shell --attach without a server fails cleanly" 1 "${TEL[@]}" shell --attach http://127.0.0.1:9/mcp -c 'fleet'
contains "unreachable attach is explained" "cannot connect to MCP server"
not_contains "unreachable attach leaks no traceback" "Traceback"

# ---------------------------------------------------------------------------
section "Stream"
# ---------------------------------------------------------------------------
# Warm the import path so SIGINT lands in the stream loop, not in imports.
uv run python -c 'import telematics.cli.main' >/dev/null 2>&1 || true

run_timeout "stream --json runs until interrupted" 124 8 \
  "${TEL[@]}" stream --vehicles 2 --seed 7 --json --rate 5
validate_json_lines "stream --json emits valid JSON" "$OUT"
contains "stream prints its sampling summary" "priority issues retained"
not_contains "stream --json emits no traceback" "Traceback"

run_timeout "stream --hex --json emits full frame bytes" 124 8 \
  "${TEL[@]}" stream --vehicles 1 --seed 7 --vehicle TRK-0001 --stage rx --hex --json --rate 5
matches "stream --hex includes a full hex frame" '"hex":"[0-9a-f]{16,}"'
contains "stream filters by vehicle" "TRK-0001"

run_timeout "stream --issues-only filters normal events" 124 8 \
  "${TEL[@]}" stream --vehicles 2 --seed 7 --stage rx --issues-only --rate 5
not_contains "issues-only suppresses normal RX lines" "received frame"

run_timeout "stream accepts --stage and --vehicle" 124 8 \
  "${TEL[@]}" stream --vehicles 3 --seed 7 --vehicle LRY-0001 --stage store --rate 1
contains "stage filter keeps STORE events" "STORE"

run "stream rejects --vehicles 0" 2 "${TEL[@]}" stream --vehicles 0
run "stream rejects --vehicles 10001" 2 "${TEL[@]}" stream --vehicles 10001
run "stream rejects a negative rate" 2 "${TEL[@]}" stream --rate -5
run "stream rejects a zero rate" 2 "${TEL[@]}" stream --rate 0
run "stream rejects an unknown stage" 2 "${TEL[@]}" stream --stage bogus
run "stream rejects a non-integer rate" 2 "${TEL[@]}" stream --rate fast
run "stream rejects a non-integer seed" 2 "${TEL[@]}" stream --seed fast

# ---------------------------------------------------------------------------
section "Serve and inject"
# ---------------------------------------------------------------------------
run_stdin "serve --transport stdio exits on EOF" 0 /dev/null \
  timeout 8 "${TEL[@]}" serve --vehicles 2 --seed 3 --transport stdio
not_contains "stdio server exits without a traceback" "Traceback"

if start_server; then
  pass "serve --transport streamable-http starts on 127.0.0.1:$PORT"
else
  fail "serve --transport streamable-http did not start"
  if [[ -f "$TMP/serve.log" ]]; then
    tail -n 12 "$TMP/serve.log" | sed 's/^/       /'
  fi
fi

if [[ "$SERVER_READY" -eq 1 ]]; then
  URL="http://127.0.0.1:$PORT/mcp"

  run "attached shell lists the fleet" 0 "${TEL[@]}" shell --attach "$URL" -c 'fleet'
  contains "attached fleet has 20 vehicles" "20 vehicles"
  contains "attached fleet is healthy" "PASS 20 WARN 0 BLOCK 0"

  run "attached shell lists tools" 0 "${TEL[@]}" shell --attach "$URL" -c 'tools'
  contains "attached tools include inject_fault" "inject_fault"
  contains "attached tools include get_quality_report" "get_quality_report"

  run "attached shell gets a location" 0 "${TEL[@]}" shell --attach "$URL" -c 'get TRK-0001'
  contains "attached get names the vehicle" "TRK-0001"

  run "attached shell injects a fault" 0 "${TEL[@]}" shell --attach "$URL" -c \
    'inject gps_drift TRK-0002 --severity high'
  contains "attached inject reports the fault" "gps_drift on TRK-0002 (high)"

  run "attached clear succeeds" 0 "${TEL[@]}" shell --attach "$URL" -c 'clear all'
  contains "attached clear reports the count" "cleared"

  run "attached advance is rejected" 1 "${TEL[@]}" shell --attach "$URL" -c 'advance 1m'
  contains "attached advance explains the mode" "only in embedded mode"
  run "attached pause is rejected" 1 "${TEL[@]}" shell --attach "$URL" -c 'pause'
  run "attached resume is rejected" 1 "${TEL[@]}" shell --attach "$URL" -c 'resume'
  run "attached speed is rejected" 1 "${TEL[@]}" shell --attach "$URL" -c 'speed'
  run "attached reset is rejected" 1 "${TEL[@]}" shell --attach "$URL" -c 'reset'
  run "attached seed is rejected" 1 "${TEL[@]}" shell --attach "$URL" -c 'seed 5'
  run "attached faults is rejected" 1 "${TEL[@]}" shell --attach "$URL" -c 'faults'

  run "inject --wait observes the expected BLOCK" 0 \
    "${TEL[@]}" inject gps_drift --vehicle TRK-0001 --severity high --duration 10m \
    --url "$URL" --wait 15s --expect BLOCK
  contains "inject confirms the injection" "injected gps_drift on TRK-0001"
  contains "inject observes BLOCK" "observed expected BLOCK verdict for TRK-0001"

  run "inject supports --duration and a fault alias" 0 \
    "${TEL[@]}" inject blackout --vehicle LRY-0001 --severity low --duration 5m --url "$URL"
  contains "inject canonicalises the alias" "injected rural_blackout on LRY-0001"

  run "inject rejects an unknown fault" 2 \
    "${TEL[@]}" inject nonsense --vehicle TRK-0001 --url "$URL"
  contains "argparse names the unknown fault" "unknown fault: nonsense"

  run "inject rejects a zero duration" 2 \
    "${TEL[@]}" inject gps_drift --vehicle TRK-0001 --duration 0m --url "$URL"
  contains "argparse explains the duration bound" "duration must be positive"

  run "inject rejects a malformed duration" 2 \
    "${TEL[@]}" inject gps_drift --vehicle TRK-0001 --duration tomorrow --url "$URL"

  run "inject rejects an unknown vehicle" 2 \
    "${TEL[@]}" inject gps_drift --vehicle FAKE-9999 --url "$URL"
  contains "server rejection is explained" "simulator rejected the request"
else
  fail "server-dependent inject and attach tests were skipped"
fi

run "inject reports an unreachable server" 3 \
  "${TEL[@]}" inject gps_drift --vehicle TRK-0001 --url http://127.0.0.1:9/mcp
contains "unreachable inject suggests serve" "uv run telematics serve"

if [[ -f "$TMP/serve.log" ]]; then
  not_contains_in "server log has no traceback" "$TMP/serve.log" "Traceback"
fi

if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
  kill -TERM -- "-$SERVER_PID" 2>/dev/null || kill -TERM "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
fi
SERVER_PID=""

# ---------------------------------------------------------------------------
section "Static report"
# ---------------------------------------------------------------------------
HTML="$TMP/report.html"
run "report accepts every input flag" 0 "${TEL[@]}" report \
  --vehicles 6 --seed 11 \
  --inject stale:TRK-0001:high --inject drift:LRY-0001:low \
  --duration 20m --fault-duration 5m --detail 3 \
  --profile-mix trk=50,lry=50 --out "$HTML"
[[ -f "$HTML" ]] && pass "report wrote the requested file" || fail "report file missing"
contains "report reports its output path" "wrote report to $HTML"
contains_in "report shows the detail limit" "$HTML" "showing 3 of 6"
contains_in "report lists injected faults" "$HTML" "stale_device on TRK-0001"
contains_in "report includes a CSP meta tag" "$HTML" "Content-Security-Policy"
contains_in "report CSP blocks all network sources" "$HTML" "default-src &#x27;none&#x27;"
not_contains_in "report has no script tags" "$HTML" "<script"
not_contains_in "report has no http URLs" "$HTML" "http://"
not_contains_in "report has no https URLs" "$HTML" "https://"
not_contains_in "report has no src attributes" "$HTML" "src="
not_contains_in "report has no href attributes" "$HTML" "href="
not_contains_in "report has no CSS imports" "$HTML" "@import"
not_contains_in "report has no CSS url()" "$HTML" "url("

run "report --clean writes a baseline" 0 "${TEL[@]}" report --vehicles 3 --seed 5 --clean --out "$TMP/clean.html"
contains "clean report has no injected faults" "wrote report"
contains_in "clean report shows the baseline scenario" "$TMP/clean.html" "clean baseline"

cat >"$TMP/scenario.yaml" <<'YAML'
name: e2e-drill
seed: 7
vehicles: 5
duration: 30m
faults:
  - fault: gps_drift
    vehicle_id: TRK-0001
    severity: high
  - fault: stale_device
    vehicle_id: LRY-0001
    severity: low
YAML
run "report --scenario loads a YAML drill" 0 "${TEL[@]}" report --scenario "$TMP/scenario.yaml" --out "$TMP/scenario.html"
contains_in "scenario name is rendered" "$TMP/scenario.html" "e2e-drill"
contains_in "scenario faults are rendered" "$TMP/scenario.html" "gps_drift on TRK-0001"

cat >"$TMP/escaped.yaml" <<'YAML'
name: "<script>alert(1)</script>"
seed: 1
vehicles: 1
duration: 5m
faults: []
YAML
run "report escapes a hostile scenario name" 0 "${TEL[@]}" report --scenario "$TMP/escaped.yaml" --out "$TMP/escaped.html"
not_contains_in "escaped scenario keeps no script tag" "$TMP/escaped.html" "<script"
contains_in "escaped scenario is HTML-escaped" "$TMP/escaped.html" "&lt;script&gt;"

run "report --open runs without opening a real browser" 0 \
  env BROWSER=/bin/true "${TEL[@]}" report --vehicles 2 --seed 3 --clean --out "$TMP/open.html" --open
[[ -f "$TMP/open.html" ]] && pass "--open still writes the report" || fail "--open skipped the report"

run "report is deterministic for the same options" 0 "${TEL[@]}" report \
  --vehicles 4 --seed 9 --inject stale:TRK-0001:high --duration 20m --out "$TMP/deterministic-a.html"
run "report deterministic rerun" 0 "${TEL[@]}" report \
  --vehicles 4 --seed 9 --inject stale:TRK-0001:high --duration 20m --out "$TMP/deterministic-b.html"
if diff -q "$TMP/deterministic-a.html" "$TMP/deterministic-b.html" >/dev/null; then
  pass "report HTML is byte-identical for the same seed and options"
else
  fail "report HTML changed for the same seed and options"
fi

mkdir -p "$TMP/default-report"
run_in "report uses the default output path" 0 "$TMP/default-report" \
  "$TEL_BIN" report --vehicles 2 --seed 3
[[ -f "$TMP/default-report/fleet-report.html" ]] && pass "default fleet-report.html created" || fail "default report missing"

run "report rejects --clean with --inject" 2 "${TEL[@]}" report --clean --inject stale:TRK-0001 --out "$TMP/x.html"
contains "clean/inject conflict is explained" "--clean cannot be combined with --inject"
run "report rejects a malformed inject spec" 2 "${TEL[@]}" report --inject broken --out "$TMP/x.html"
run "report rejects an unknown injection vehicle" 2 "${TEL[@]}" report --vehicles 2 --inject stale:FAKE-9999 --out "$TMP/x.html"
run "report rejects --detail 0" 2 "${TEL[@]}" report --detail 0 --out "$TMP/x.html"
run "report rejects --detail 201" 2 "${TEL[@]}" report --detail 201 --out "$TMP/x.html"
run "report rejects --duration 0m" 2 "${TEL[@]}" report --duration 0m --out "$TMP/x.html"
run "report rejects --fault-duration 0m" 2 "${TEL[@]}" report --fault-duration 0m --out "$TMP/x.html"
run "report rejects a profile mix below 100" 2 "${TEL[@]}" report --profile-mix trk=50 --out "$TMP/x.html"
run "report rejects --vehicles 0" 2 "${TEL[@]}" report --vehicles 0 --out "$TMP/x.html"
run "report rejects a bad seed" 2 "${TEL[@]}" report --seed nope --out "$TMP/x.html"
run "report reports a missing scenario file" 2 "${TEL[@]}" report --scenario "$TMP/missing.yaml" --out "$TMP/x.html"
run "report reports an unwritable output path" 4 "${TEL[@]}" report --vehicles 2 --out /nonexistent-dir/report.html

# ---------------------------------------------------------------------------
section "Evaluation"
# ---------------------------------------------------------------------------
run "deterministic eval passes" 0 "${TEL[@]}" eval --seed 5
contains "eval reports scenario count" "Deterministic eval: 3 scenarios"
contains "eval passes every assertion" "18/18 assertions passed"
contains "eval reports the stale-device scenario" "PASS stale_device"
contains "eval reports the drift scenario" "PASS gps_drift"
contains "eval reports the blackout scenario" "PASS rural_blackout"

run "eval --date and --out write evidence" 0 "${TEL[@]}" eval --seed 5 --date 2026-11-15 --out "$TMP/eval.md"
contains "eval confirms the evidence path" "Deterministic eval results written to $TMP/eval.md"
[[ -f "$TMP/eval.md" ]] && pass "eval evidence file exists" || fail "eval evidence file missing"
contains_in "eval evidence records the date" "$TMP/eval.md" "Date: 2026-11-15"
contains_in "eval evidence records the seed" "$TMP/eval.md" 'Seed: `5`'

printf 'y\nn\ny\n' >"$TMP/manual-answers.txt"
run_stdin "eval --manual grades the fixed rubric" 0 "$TMP/manual-answers.txt" "${TEL[@]}" eval --manual
contains "manual eval reports the score" "Manual eval: 2/3 rubric passes"
contains "manual eval reports the question-set hash" "Question-set SHA-256:"

run "eval --out requires --date" 2 "${TEL[@]}" eval --out "$TMP/eval.md"
contains "missing date is explained" "writing eval evidence requires --date YYYY-MM-DD"
run "eval rejects --manual with --out" 2 "${TEL[@]}" eval --manual --out "$TMP/eval.md"
contains "manual conflict is explained" "--manual cannot be combined with --model or --out"
run "eval rejects a malformed date" 2 "${TEL[@]}" eval --date 15-11-2026 --out "$TMP/eval.md"
contains "malformed date is explained" "date must use YYYY-MM-DD format"
run "eval --model requires an API key" 2 \
  env -u GEMINI_API_KEY -u GOOGLE_API_KEY "${TEL[@]}" eval --model gemini-2.5-flash \
  --date 2026-11-15 --out "$TMP/model.md"
contains "missing API key is explained" "set GEMINI_API_KEY or GOOGLE_API_KEY"
run "eval --model without --date is rejected" 2 \
  env -u GEMINI_API_KEY -u GOOGLE_API_KEY "${TEL[@]}" eval --model gemini-2.5-flash --out "$TMP/model.md"

# ---------------------------------------------------------------------------
section "Boundaries: unknown commands and large fleet"
# ---------------------------------------------------------------------------
run "unknown subcommand is rejected" 2 "${TEL[@]}" nope
contains "unknown subcommand lists the choices" "invalid choice: 'nope'"
run "no subcommand is rejected" 2 "${TEL[@]}"
run "serve rejects --port 0" 2 "${TEL[@]}" serve --port 0
run "serve rejects --speed 0" 2 "${TEL[@]}" serve --speed 0
run "serve rejects an unknown transport" 2 "${TEL[@]}" serve --transport udp

cat >"$TMP/large.tqs" <<'TQS'
fleet
inject gps_drift TRK-0001 --severity high
advance 2m
fleet
ls --worse-than WARN
exit
TQS
run "600-vehicle fleet isolates one injected fault" 0 \
  "${TEL[@]}" shell --vehicles 600 --seed 42 --script "$TMP/large.tqs"
contains "600-vehicle baseline is healthy" "PASS 600 WARN 0 BLOCK 0"
contains "600-vehicle fleet reports exactly one BLOCK" "PASS 599 WARN 0 BLOCK 1"
matches "large-fleet filter prints the blocked vehicle" 'TRK-0001 .*BLOCK'
matching_line_count_equals "large-fleet filtered output has one row" "⛔ BLOCK" 1

# ---------------------------------------------------------------------------
section "Summary"
# ---------------------------------------------------------------------------
if [[ "$FAILED" -eq 0 ]]; then
  printf '\nPASS: %d checks passed, 0 failed\n' "$TOTAL"
  exit 0
fi
printf '\nFAIL: %d checks passed, %d failed\n' "$((TOTAL - FAILED))" "$FAILED"
exit 1
