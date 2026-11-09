"""Short environment checks with direct repair commands."""

import shutil
import sys
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version


def diagnose_environment(
    *,
    python_version: tuple[int, int, int],
    uv_available: bool,
    package_available: bool,
) -> tuple[str, ...]:
    """Return one compact status line per supported environment check."""
    results: list[str] = []
    if python_version >= (3, 12, 0):
        results.append(f"OK Python {python_version[0]}.{python_version[1]}+")
    else:
        results.append("FAIL Python 3.12+ required — run: uv python install 3.12")
    if uv_available:
        results.append("OK uv available")
    else:
        results.append(
            "FAIL uv not found — install it: https://docs.astral.sh/uv/getting-started/installation/"
        )
    if package_available:
        results.append("OK package installed")
    else:
        results.append("FAIL package not installed — run: uv sync")
    return tuple(results)


def doctor() -> int:
    """Print the current environment diagnosis and return a status code."""
    try:
        version("telematics-quality-kit")
        installed = True
    except PackageNotFoundError:
        installed = False
    results: Sequence[str] = diagnose_environment(
        python_version=(
            sys.version_info.major,
            sys.version_info.minor,
            sys.version_info.micro,
        ),
        uv_available=shutil.which("uv") is not None,
        package_available=installed,
    )
    for line in results:
        print(line)
    return int(any(line.startswith("FAIL") for line in results))
