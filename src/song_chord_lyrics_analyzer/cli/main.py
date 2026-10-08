"""The ``songlab`` command line interface.

The CLI is the laboratory front end of the analysis engine (roadmap section
47). It contains no analysis logic: it parses arguments, calls the application
services and turns expected failures into short, actionable messages
(roadmap section 63).
"""

from __future__ import annotations

import argparse
import sys
import traceback
from collections.abc import Sequence

from song_chord_lyrics_analyzer import CLI_NAME, PROJECT_NAME, __version__
from song_chord_lyrics_analyzer.cli.commands import (
    analyze,
    benchmark,
    chords,
    doctor,
    gui,
    info,
    play,
)
from song_chord_lyrics_analyzer.utils.errors import SongLabError
from song_chord_lyrics_analyzer.utils.logging import configure_logging, get_logger

__all__ = ["build_parser", "main"]

_logger = get_logger("cli")

EPILOG = """\
Commands:
  info       inspect an audio file and report its metadata
  doctor     report environment, dependency and engine status
  chords     detect chords with a selectable engine
  analyze    run the full pipeline and assemble the canonical document
  play       play an audio file and watch the chord under the playhead change
  gui        open the desktop window (needs the optional "gui" extra)
  benchmark  score benchmark cases, optionally running an engine

Planned commands (added phase by phase, see ROADMAP.md):
  lyrics    transcribe lyrics with word-level timestamps
  compare   compare several engines on the same song
  separate  separate the mix into stems
  fuse      combine engine results into one consensus analysis
  export    export the canonical document (JSON, ChordPro, ...)

Environment variables:
  SONGLAB_FFMPEG, SONGLAB_FFPROBE   explicit paths to the FFmpeg tools
  SONGLAB_CACHE_DIR                 analysis cache location
  SONGLAB_DATA_DIR                  application data location
  SONGLAB_TEMP_DIR                  temporary file location
"""


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog=CLI_NAME,
        description=(
            "Song Chord Lyrics Analyzer - a local, offline-first laboratory that "
            "extracts synchronized lyrics, chords, beats, tempo and key from audio."
        ),
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{PROJECT_NAME} {__version__}",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="increase log verbosity (repeatable)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="only report warnings and errors",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="enable debug logging and print full tracebacks",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND", title="commands")

    info_parser = subparsers.add_parser(
        "info",
        help="inspect an audio file and report its metadata",
        description=(
            "Inspect an audio file and report technical metadata. WAV files are "
            "read with the standard library; other formats require FFmpeg."
        ),
    )
    info.add_arguments(info_parser)
    info_parser.set_defaults(handler=info.run)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="report environment, dependency and engine status",
        description="Report the Python environment, FFmpeg availability and registered engines.",
    )
    doctor.add_arguments(doctor_parser)
    doctor_parser.set_defaults(handler=doctor.run)

    chords_parser = subparsers.add_parser(
        "chords",
        help="detect chords in an audio file with a selectable engine",
        description=(
            "Estimate chords for an audio file with a registered chord engine "
            "(default: the first available one). Use --engine NAME to select a "
            "specific engine, e.g. chroma-baseline. The run cost comes from the "
            "section 45 performance harness."
        ),
    )
    chords.add_arguments(chords_parser)
    chords_parser.set_defaults(handler=chords.run)

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="run chords, key and tempo engines and assemble the canonical document",
        description=(
            "Analyse one audio file with the registered chord, key and tempo "
            "engines and assemble the canonical document with its provenance. "
            "A layer whose engine is unavailable is reported as skipped and the "
            "rest of the analysis is kept. Lyrics are not analysed yet: no "
            "lyrics engine is registered."
        ),
    )
    analyze.add_arguments(analyze_parser)
    analyze_parser.set_defaults(handler=analyze.run)

    play_parser = subparsers.add_parser(
        "play",
        help="play an audio file and show the chord under the playhead",
        description=(
            "Open one audio file, analyse it and follow it while it plays, "
            "showing the chord under the playhead. This is the first product "
            "command (roadmap Phase C): analysis, playback and the synchronized "
            "display come from the same application session. Use --at SECONDS "
            "to print the chord at one position without playing anything."
        ),
    )
    play.add_arguments(play_parser)
    play_parser.set_defaults(handler=play.run)

    gui_parser = subparsers.add_parser(
        "gui",
        help='open the desktop window (needs the optional "gui" extra)',
        description=(
            "Open the minimal desktop window (roadmap Phase D): open an audio "
            "file, see its waveform timeline and its chords, play, pause, seek "
            "and always see the chord under the playhead. The window renders "
            "the same application session as 'songlab play', so it needs "
            'PyQt6 (pip install "song-chord-lyrics-analyzer[gui]").'
        ),
    )
    gui.add_arguments(gui_parser)
    gui_parser.set_defaults(handler=gui.run)

    benchmark_parser = subparsers.add_parser(
        "benchmark",
        help="score benchmark cases, optionally running an engine to produce them",
        description=(
            "Score a directory of benchmark cases (a reference/hypothesis pair per "
            "song) with the section 44 metrics and write benchmark/{json,csv,md}. "
            "With --engine, every case that declares an 'audio' file is first run "
            "through that registered chord engine, and the measured run cost fills "
            "the report; without it, stored results are scored as they are."
        ),
    )
    benchmark.add_arguments(benchmark_parser)
    benchmark_parser.set_defaults(handler=benchmark.run)

    return parser


def _report_error(error: SongLabError, *, debug: bool) -> None:
    """Print an expected failure the way a user can act on it."""
    print(f"Error: {error.message}", file=sys.stderr)
    if error.hint:
        print("", file=sys.stderr)
        print(error.hint, file=sys.stderr)
    if debug:
        _logger.debug("details", exc_info=error)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    verbosity = 2 if args.debug else (-1 if args.quiet else args.verbose)
    logger = configure_logging(verbosity)

    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0

    try:
        return int(handler(args))
    except SongLabError as error:
        _report_error(error, debug=args.debug)
        return error.exit_code
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        return 130
    except BrokenPipeError:  # pragma: no cover - happens when piping into `head`
        return 0
    except Exception as error:  # the CLI must never leak a traceback to the user
        logger.debug("unexpected failure", exc_info=True)
        print(
            f"Unexpected error: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        if args.debug:
            traceback.print_exc()
        else:
            print("Run the command again with --debug for the full traceback.", file=sys.stderr)
        return 1
