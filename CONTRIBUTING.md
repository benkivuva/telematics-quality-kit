# Contributing

Thanks for helping improve telematics-quality-kit. Contributions should keep the project a deterministic, synthetic-data testbed for developers. It does not manage fleets, connect to real vehicles, or send device commands.

## Before you start

- Check the open issues and pull requests for related work.
- For a substantial change, open an issue first to agree on scope.
- Keep changes within the current release scope. Features marked for a later version in the architecture are not ready to implement.
- Use synthetic identifiers and data in tests, examples, and reports. Never commit real device identifiers, locations, telemetry captures, credentials, or `.env` files.

## Set up the development environment

You need Python 3.12 or newer, Git, and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/benkivuva/telematics-quality-kit.git
cd telematics-quality-kit
uv sync
uv run telematics doctor
```

`uv sync` installs the project and its development tools from the lockfile. The doctor command checks the local environment.

## Test-driven changes

Start with a failing test for a bug or new behavior, then make the smallest change that passes it. Put tests in the matching tier under `tests/`:

- `tests/unit/` for focused component behavior.
- `tests/integration/` for interactions such as MCP client/server behavior.
- `tests/property/` for invariants over generated inputs.
- `tests/cli/` for command-line, shell, stream, fault-injection, and report behavior.

Protocol changes require encoder/decoder round-trip tests and fixture provenance. Quality-check changes require property coverage. Never change a golden vector just to make a test pass, weaken a test or gate to get a green build, or add unmeasured performance claims.

Run the narrowest relevant test while iterating, then run the full verification gate before opening a pull request:

```bash
uv run pytest tests/cli
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/telematics
make verify
```

`make verify` runs Ruff lint and format checks, strict mypy over `src/telematics`, and the full pytest suite. `make security` runs gitleaks, Semgrep, pip-audit, and Trivy filesystem and image scans; Docker and those scanner tools must be installed to run the complete target.

## Coding and security expectations

- Follow the architecture contract and existing module boundaries.
- Preserve deterministic output: use the injected clock and seeded randomness; do not use wall-clock time in output-producing logic.
- Keep protocol parsing safe and route data through the real decoders.
- Use bound SQL parameters, escape dynamic HTML, and keep reports self-contained.
- Keep HTTP bound to loopback by default. Do not use wildcard bind addresses in defaults or examples.
- Pin GitHub Actions to full commit SHAs and give each workflow only the permissions it needs.
- Explain the reason for any dependency change and update the lockfile; run the dependency audit.
- Keep changes focused. Do not add scaffolding for future-version features.

## Commit messages

Use Conventional Commit subjects in imperative mood, lowercase, with no trailing period and no more than 72 characters:

```text
<type>(<scope>): <subject>
```

Types: `feat`, `fix`, `test`, `refactor`, `docs`, `chore`, `perf`.

Common scopes: `codec`, `ingest`, `sim`, `store`, `checks`, `score`, `mcp`, `cli`, `report`, `ci`, `deps`.

Keep each commit to one logical change. Stage explicit paths; do not use `git add .` or `git add -A`. Never commit secrets, local-only project instructions, or generated artifacts.

## Pull requests

Create a feature branch and open a pull request against `main`. The `main` branch is protected; changes must go through a pull request, and all required CI checks must pass before merge. Do not push directly to `main`.

In the pull request description, explain the user problem, the behavior changed, and how you tested it. Link related issues. Include screenshots only when they help review a report or other visual output, and use synthetic data.

CI runs lint, formatting, typing, and tests across Linux, macOS, and Windows. It also runs the package quickstart and container smoke checks. Security CI runs gitleaks, Semgrep, pip-audit, and Trivy. Resolve failures or explain a reproducible infrastructure issue; do not weaken a gate to make the pull request pass.

## Reporting security issues

Please use the private vulnerability reporting instructions in [SECURITY.md](SECURITY.md), rather than filing a public issue for an unpatched vulnerability.
