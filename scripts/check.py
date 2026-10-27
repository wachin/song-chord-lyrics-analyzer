#!/usr/bin/env python3
"""Run the repository gate with the interpreter you invoke.

This is the single command a human or an AI agent should run before claiming
work is done::

    python scripts/check.py

It runs the same four checks as CI and the contributor guide, from the
repository root, with the current Python interpreter:

1. ``ruff check .``
2. ``ruff format --check .``
3. ``python -m mypy``
4. ``python -m pytest -q``

Using ``sys.executable`` matters: an agent that activates a virtual environment
and runs this script gets that environment's tools, not whatever ``ruff``
happens to be first on ``PATH``. On a headless Linux box the script exports
``QT_QPA_PLATFORM=offscreen`` unless the caller already chose a platform, so the
window tests do not need a display. Pass ``--quick`` to run only the static
checks, or ``--tests-only`` to run only pytest.

The script does not install anything and does not touch the network. If a tool
is missing it prints the install command from ``docs/DEVELOPMENT.md`` and exits
with status 2 instead of a confusing traceback.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shlex
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Import name -> human name, in the order the gate runs.
_TOOLS = {
    "ruff": "ruff",
    "mypy": "mypy",
    "pytest": "pytest",
}


def _missing_tools(*, quick: bool, tests_only: bool) -> list[str]:
    """Tools the current interpreter cannot import for the selected mode."""
    if quick:
        names = ("ruff", "mypy")
    elif tests_only:
        names = ("pytest",)
    else:
        names = tuple(_TOOLS)
    return [name for name in names if importlib.util.find_spec(name) is None]


def _commands(*, quick: bool, tests_only: bool) -> list[tuple[str, list[str]]]:
    """The gate commands for the selected mode."""
    static = [
        ("Ruff lint", [sys.executable, "-m", "ruff", "check", "."]),
        ("Ruff format", [sys.executable, "-m", "ruff", "format", "--check", "."]),
        ("Mypy", [sys.executable, "-m", "mypy"]),
    ]
    tests = [("Pytest", [sys.executable, "-m", "pytest", "-q"])]
    if quick:
        return static
    if tests_only:
        return tests
    return [*static, *tests]


def _display(command: Sequence[str]) -> str:
    """A readable command line for the log, cross-platform."""
    return " ".join(shlex.quote(part) for part in command)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the gate and return a process exit status."""
    parser = argparse.ArgumentParser(
        description="Run the song-chord-lyrics-analyzer verification gate."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--quick",
        action="store_true",
        help="run ruff and mypy only (skip pytest)",
    )
    mode.add_argument(
        "--tests-only",
        action="store_true",
        help="run pytest only (skip ruff and mypy)",
    )
    args = parser.parse_args(argv)

    missing = _missing_tools(quick=args.quick, tests_only=args.tests_only)
    if missing:
        names = ", ".join(_TOOLS[name] for name in missing)
        print(
            f"Missing development tool(s): {names}.",
            file=sys.stderr,
        )
        print(
            'Install the documented environment with: python -m pip install -e ".[dev,gui]"',
            file=sys.stderr,
        )
        print(
            "For the DSP/playback/window suite use: "
            'python -m pip install -e ".[dev,dsp,playback,gui]"',
            file=sys.stderr,
        )
        return 2

    environment = os.environ.copy()
    if sys.platform.startswith("linux") and "QT_QPA_PLATFORM" not in environment:
        environment["QT_QPA_PLATFORM"] = "offscreen"
        print("QT_QPA_PLATFORM=offscreen (set explicitly by this script on Linux)")

    print(f"Repository: {ROOT}")
    print(f"Python: {sys.version.split()[0]} ({sys.executable})")
    print(f"Platform: {sys.platform}")
    print()

    failed: list[str] = []
    for label, command in _commands(quick=args.quick, tests_only=args.tests_only):
        print(f"==> {label}: {_display(command)}", flush=True)
        completed = subprocess.run(command, cwd=ROOT, env=environment, check=False)
        if completed.returncode != 0:
            failed.append(label)
            print(f"<== {label} failed (exit {completed.returncode})", file=sys.stderr)
        else:
            print(f"<== {label} passed")
        print(flush=True)

    if failed:
        print("Gate failed: " + ", ".join(failed), file=sys.stderr)
        return 1
    print("Gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
