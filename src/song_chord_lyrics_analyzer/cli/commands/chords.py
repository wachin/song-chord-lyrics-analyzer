"""``songlab chords`` - detect chords in one audio file (roadmap section 47).

The first analysis command. It resolves a chord engine through the registry
(``--engine NAME`` selects one explicitly; otherwise the first available chord
engine is used), runs it on a single file and prints either a readable chord
list with the measured section 45 run cost or the canonical JSON result.

The command contains no analysis logic: argument validation, engine selection
and presentation live here, the estimation itself stays behind the
``ChordEngine`` protocol so adding an engine never changes this file.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from song_chord_lyrics_analyzer.cli.commands.info import format_bytes
from song_chord_lyrics_analyzer.engines import EngineKind, create_default_registry
from song_chord_lyrics_analyzer.engines.base import ChordAnalysisOptions
from song_chord_lyrics_analyzer.models.analysis import EngineResult
from song_chord_lyrics_analyzer.performance import real_time_factor
from song_chord_lyrics_analyzer.schema.codec import encode
from song_chord_lyrics_analyzer.utils.errors import DependencyError, InputError

__all__ = ["add_arguments", "format_report", "resolve_engine", "run"]


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register ``songlab chords`` arguments."""
    parser.add_argument("audio", type=Path, help="audio file to analyse")
    parser.add_argument(
        "--engine",
        metavar="NAME",
        default=None,
        help="registered chord engine to use (default: the first available one)",
    )
    parser.add_argument(
        "--start",
        type=float,
        default=None,
        metavar="SECONDS",
        help="analyse from this offset instead of the beginning",
    )
    parser.add_argument(
        "--end",
        type=float,
        default=None,
        metavar="SECONDS",
        help="stop analysis at this absolute time",
    )
    parser.add_argument(
        "--min-duration",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="merge chords shorter than this into a neighbour (default: 0, no merging)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the canonical engine result as JSON",
    )


def resolve_engine(name: str | None) -> Any:
    """Return the chord engine to run.

    An explicit ``name`` must be registered for the ``chords`` kind. Without
    one, the first *available* chord engine is chosen, so a missing optional
    dependency never becomes a silent default; when none is available the
    first registered name is returned anyway, letting the engine itself raise a
    dependency error with an install hint.
    """
    registry = create_default_registry()
    kind = EngineKind.CHORDS
    if name is not None:
        return registry.get(kind, name)
    available = registry.available(kind)
    if available:
        return registry.get(kind, available[0])
    registered = registry.names(kind)
    if not registered:
        raise InputError(
            "No chord engine is registered.",
            hint="Engines are added phase by phase; run 'songlab doctor' to list them.",
        )
    return registry.get(kind, registered[0])


def _options(args: argparse.Namespace) -> ChordAnalysisOptions:
    """Validate the time-selection flags and build the engine options."""
    if args.start is not None and args.start < 0.0:
        raise InputError("--start must not be negative.", hint="Times are seconds from the start.")
    if args.end is not None and args.end < 0.0:
        raise InputError("--end must not be negative.", hint="Times are seconds from the start.")
    if args.end is not None and args.start is not None and args.end <= args.start:
        raise InputError("--end must be greater than --start.")
    if args.min_duration < 0.0:
        raise InputError("--min-duration must not be negative.")
    return ChordAnalysisOptions(
        start=args.start,
        end=args.end,
        minimum_duration=args.min_duration,
    )


def format_report(result: EngineResult) -> str:
    """Render a readable chord list with the measured section 45 run cost."""
    performance = result.metadata.get("performance")
    performance = performance if isinstance(performance, dict) else {}
    audio_seconds = performance.get("audio_seconds")
    audio_value = float(audio_seconds) if isinstance(audio_seconds, (int, float)) else None

    engine_line = f"{result.engine} {result.engine_version or ''}".rstrip()
    lines = ["Chords", "======", f"File:     {result.audio_path}", f"Engine:   {engine_line}"]
    if audio_value is not None:
        lines.append(f"Duration: {audio_value:.3f} s")
    lines.append(f"Chords:   {len(result.chords)}")
    lines.append("")
    lines.append("   start      end   label")
    for event in result.chords:
        label = event.label or event.to_label()
        if event.end is None:
            lines.append(f"  {event.start:8.3f}        -   {label}")
        else:
            lines.append(f"  {event.start:8.3f} {event.end:8.3f}   {label}")

    processing = result.processing_time_seconds
    if processing is not None:
        lines.append("")
        lines.append("Performance")
        lines.append("-----------")
        lines.append(f"Processing:       {processing:.3f} s")
        factor = real_time_factor(audio_value, processing)
        if factor is not None:
            lines.append(f"Real-time factor: {factor:.2f}")
        peak = performance.get("peak_rss_bytes")
        if isinstance(peak, int):
            lines.append(f"Peak RSS:         {format_bytes(peak)}")
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    """Execute ``songlab chords``."""
    options = _options(args)
    engine = resolve_engine(args.engine)
    if not engine.is_available():
        raise DependencyError(
            f"Engine {engine.name!r} is not available in this environment.",
            hint=(
                "Install the engine's optional dependencies, or pick another engine "
                "('songlab doctor' lists the registered ones)."
            ),
        )
    result = engine.analyze(args.audio, options)
    if args.json:
        print(json.dumps(encode(result), indent=2, ensure_ascii=False))
        return 0
    print(format_report(result))
    return 0
