"""``songlab play`` - watch the chords follow the song (roadmap Phase C).

This is the first *product* command rather than a laboratory one: it opens one
audio file through the application session layer, plays it and keeps drawing the
chord under the playhead - the roadmap's link 7, "synchronized chord display",
in its smallest honest form.

It holds no analysis, playback or synchronization logic; that lives in
:mod:`song_chord_lyrics_analyzer.app`. This module only parses arguments, prints
a short header and hands the session to
:class:`~song_chord_lyrics_analyzer.app.display.ConsoleDisplay`. The session owns
the player, so a machine with no audio output still gets an honest dependency
error instead of silence, and ``--at`` answers "which chord is here?" without
playing anything at all (which is also how the CI checks this command).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from song_chord_lyrics_analyzer.app import (
    DEFAULT_REFRESH_INTERVAL,
    ConsoleDisplay,
    SongSession,
    follow,
)
from song_chord_lyrics_analyzer.cli.commands.analyze import parse_engine_overrides
from song_chord_lyrics_analyzer.models.analysis import AnalysisResult
from song_chord_lyrics_analyzer.utils.errors import InputError
from song_chord_lyrics_analyzer.utils.time import format_timestamp

__all__ = ["add_arguments", "format_header", "run"]


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register ``songlab play`` arguments."""
    parser.add_argument("audio", type=Path, help="audio file to play and follow")
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
        "--at",
        type=float,
        default=None,
        metavar="SECONDS",
        help="print the chord at this position and exit, without playing anything",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_REFRESH_INTERVAL,
        metavar="SECONDS",
        help="seconds between two refreshes of the display (default: 0.1)",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=None,
        metavar="N",
        help="stop after N display frames instead of playing to the end",
    )
    parser.add_argument(
        "--no-inline",
        action="store_true",
        help="print one line per refresh instead of redrawing the line in place",
    )
    parser.add_argument(
        "--no-hash",
        action="store_true",
        help="skip the SHA-256 of the input in provenance (faster on large files)",
    )


def format_header(document: AnalysisResult, path: Path, duration: float) -> str:
    """Render the two or three lines printed before the live display."""
    lines = [
        "Playing",
        "=======",
        f"File:     {path}",
        f"Duration: {format_timestamp(duration)}",
    ]
    if document.chords:
        engines = sorted({event.source for event in document.chords if event.source})
        from_note = f" from {', '.join(engines)}" if engines else ""
        lines.append(f"Chords:   {len(document.chords)} events{from_note}")
    else:
        lines.append("Chords:   none detected")
    return "\n".join(lines)


def _validate(args: argparse.Namespace) -> None:
    """Reject impossible flags before any file is opened."""
    if args.at is not None and args.at < 0.0:
        raise InputError(
            "--at must not be negative.",
            hint="Positions are seconds from the start of the song.",
        )
    if args.interval <= 0.0:
        raise InputError(
            f"--interval must be positive, got {args.interval!r}",
            hint="Use a refresh interval such as 0.1 seconds.",
        )
    if args.frames is not None and args.frames < 1:
        raise InputError(f"--frames must be at least 1, got {args.frames!r}")


def run(args: argparse.Namespace) -> int:
    """Execute ``songlab play``."""
    _validate(args)
    overrides = parse_engine_overrides(args.engine)
    session = SongSession()
    try:
        document = session.open(
            args.audio,
            engines=overrides,
            input_hash=not args.no_hash,
        )
        display = ConsoleDisplay(inline=not args.no_inline)

        if args.at is not None:
            session.seek(min(args.at, session.duration()))
            display.show(session.snapshot())
            display.close()
            return 0

        print(format_header(document, session.path or args.audio, session.duration()))
        session.play()
        follow(session, display, interval=args.interval, max_frames=args.frames)
        return 0
    finally:
        session.close()
