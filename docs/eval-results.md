# Evaluation results

Date: 2026-11-12  
Model: not run (manual, API key required)  
Seed: `42`  
Question-set SHA-256: `66205e9f9efbaca8b2b8f7f177c03975d4bd130edb5609ba6aa33871bf7cffdd`

## Deterministic layer

Status: **PASS** — 18/18 assertions passed.

| Scenario | Assertions passed |
| --- | ---: |
| `stale_device` | 6/6 |
| `gps_drift` | 6/6 |
| `rural_blackout` | 6/6 |

Raw counts: `18` passed, `0` failed, `18` total.

The deterministic scenarios call the public in-process MCP tools after injecting a stale-device,
GPS-drift, or rural-blackout fault. Assertions cover the BLOCK verdict, disabled decision use,
caveats, and withheld trip distance.

## Manual model layer

The optional model comparison is not run by CI or by the default deterministic command. To run it
manually, set `GEMINI_API_KEY` or `GOOGLE_API_KEY` and run:

```bash
uv run telematics eval --model gemini-1.5-flash --date YYYY-MM-DD --out docs/eval-results.md
```

A model result replaces this deterministic evidence with the model identifier and raw on/off rubric
counts from that actual run. No model result is claimed here.

## Limit of this evidence

The faults are produced by this project's own noise models, so these checks show consistency with
the tool contract under synthetic conditions. They do not establish real-world failure rates or
general model behavior. Real-trace validation requires captures that users run themselves and
differential tests against independent implementations.
