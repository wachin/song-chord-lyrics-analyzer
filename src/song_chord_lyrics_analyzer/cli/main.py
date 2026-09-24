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
from song_chord_lyrics_analyzer.cli.commands import doctor, info
from song_chord_lyrics_analyzer.utils.errors import SongLabError
from song_chord_lyrics_analyzer.utils.logging import configure_logging, get_logger

__all__ = ["build_parser", "main"]

_logger = get_logger("cli")

EPILOG = """\
Planned commands (added phase by phase, see ROADMAP.md):
  lyrics    transcribe lyrics with word-level timestamps
  chords    detect chords with a selectable engine
  analyze   run the full pipeline (lyrics, chords, key, tempo, beats)
  compare   compare several engines on the same song
  separate  separate the mix into stems
  fuse      combine engine results into one consensus analysis
  export    export the canonical document (JSON, ChordPro, ...)
  benchmark evaluate engines against a dataset

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
