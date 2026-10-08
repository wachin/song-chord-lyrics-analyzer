"""``songlab gui`` - open the desktop window (roadmap Phase D).

A two-line command: parse the optional file name, then hand everything to
:func:`song_chord_lyrics_analyzer.gui.run`. The import happens inside
:func:`run` so that ``songlab gui --help``, and every other command, keep working
on an installation without PyQt6 - a missing optional dependency is reported as
an actionable error, never as a traceback.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from song_chord_lyrics_analyzer.cli.commands.analyze import parse_engine_overrides

__all__ = ["add_arguments", "run"]


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register ``songlab gui`` arguments."""
    parser.add_argument(
        "audio",
        nargs="?",
        type=Path,
        default=None,
        help="audio file to open on launch (optional: the window can open one too)",
    )
    parser.add_argument(
        "--engine",
        metavar="KIND=NAME",
        action="append",
        default=None,
        help=(
            "use this engine for one layer, e.g. --engine chords=chroma-baseline "
            "(repeatable; layers without an override use the first available engine)"
        ),
    )
    parser.add_argument(
        "--no-hash",
        action="store_true",
        help="skip the SHA-256 of the input in provenance (faster on large files)",
    )


def run(args: argparse.Namespace) -> int:
    """Execute ``songlab gui``."""
    from song_chord_lyrics_analyzer.gui import run as run_gui

    return run_gui(
        args.audio,
        engines=parse_engine_overrides(args.engine),
        input_hash=not args.no_hash,
    )
