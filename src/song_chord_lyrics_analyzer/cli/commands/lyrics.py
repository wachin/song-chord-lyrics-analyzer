"""``songlab lyrics`` - transcribe one audio file with word timestamps (Phase E).

The sibling of ``songlab chords``: it resolves a lyrics engine through the
registry (``--engine NAME`` selects one explicitly; otherwise the first
*available* lyrics engine is used) and prints either a readable, timestamped
lyric list with the measured section 45 run cost or the canonical JSON result.

Like the chord command it holds no transcription logic. The windowing and the
reassembly live in :mod:`song_chord_lyrics_analyzer.engines.lyrics_chunking`,
the model and the optional dependencies behind the ``LyricsEngine`` protocol, so
a second lyrics engine never changes this file.

The same engine is also reachable through ``songlab analyze``: registering it
adds a lyrics step to the analysis service, which reports it as *skipped* -
never as empty output - on a machine without the optional lyrics stack.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from song_chord_lyrics_analyzer.cli.commands.info import format_bytes
from song_chord_lyrics_analyzer.engines import (
    DEFAULT_CHUNK_SECONDS,
    EngineKind,
    create_default_registry,
)
from song_chord_lyrics_analyzer.engines.base import LyricsOptions
from song_chord_lyrics_analyzer.models.analysis import EngineResult
from song_chord_lyrics_analyzer.performance import real_time_factor
from song_chord_lyrics_analyzer.schema.codec import encode
from song_chord_lyrics_analyzer.utils.errors import DependencyError, InputError
from song_chord_lyrics_analyzer.utils.time import format_timestamp

__all__ = ["add_arguments", "format_report", "resolve_engine", "run"]


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register ``songlab lyrics`` arguments."""
    parser.add_argument("audio", type=Path, help="audio file to transcribe")
    parser.add_argument(
        "--engine",
        metavar="NAME",
        default=None,
        help="registered lyrics engine to use (default: the first available one)",
    )
    parser.add_argument(
        "--chunk-seconds",
        type=float,
        default=DEFAULT_CHUNK_SECONDS,
        metavar="SECONDS",
        help=(
            "window length handed to the model (default: 20). Long audio must be "
            "chunked: the packaged model cannot take a whole song"
        ),
    )
    parser.add_argument(
        "--overlap-seconds",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="how much neighbouring windows share (default: 0)",
    )
    parser.add_argument(
        "--start",
        type=float,
        default=None,
        metavar="SECONDS",
        help="transcribe from this offset instead of the beginning",
    )
    parser.add_argument(
        "--end",
        type=float,
        default=None,
        metavar="SECONDS",
        help="stop transcribing at this absolute time",
    )
    parser.add_argument(
        "--language",
        default=None,
        metavar="CODE",
        help="record this language on the segments (the model does not report one)",
    )
    parser.add_argument(
        "--no-words",
        action="store_true",
        help="keep only the segment text, without word-level timestamps",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the canonical engine result as JSON",
    )


def resolve_engine(name: str | None) -> Any:
    """Return the lyrics engine to run.

    An explicit ``name`` must be registered for the ``lyrics`` kind. Without
    one, the first *available* lyrics engine is chosen, so a missing optional
    stack never becomes a silent default; when none is available the first
    registered name is returned anyway, letting the engine itself raise a
    dependency error with an install hint.
    """
    registry = create_default_registry()
    kind = EngineKind.LYRICS
    if name is not None:
        return registry.get(kind, name)
    available = registry.available(kind)
    if available:
        return registry.get(kind, available[0])
    registered = registry.names(kind)
    if not registered:
        raise InputError(
            "No lyrics engine is registered.",
            hint="Engines are added phase by phase; run 'songlab doctor' to list them.",
        )
    return registry.get(kind, registered[0])


def _options(args: argparse.Namespace) -> LyricsOptions:
    """Validate the flags and build the engine options."""
    if args.start is not None and args.start < 0.0:
        raise InputError("--start must not be negative.", hint="Times are seconds from the start.")
    if args.end is not None and args.end < 0.0:
        raise InputError("--end must not be negative.", hint="Times are seconds from the start.")
    if args.end is not None and args.start is not None and args.end <= args.start:
        raise InputError("--end must be greater than --start.")
    if args.chunk_seconds <= 0.0:
        raise InputError(f"--chunk-seconds must be positive, got {args.chunk_seconds!r}")
    if args.overlap_seconds < 0.0:
        raise InputError("--overlap-seconds must not be negative.")
    if args.overlap_seconds >= args.chunk_seconds:
        raise InputError(
            "--overlap-seconds must be smaller than --chunk-seconds.",
            hint="An overlap as long as the window would never advance.",
        )
    return LyricsOptions(
        language=args.language,
        word_timestamps=not args.no_words,
        start=args.start,
        end=args.end,
        extra={
            "chunk_seconds": args.chunk_seconds,
            "overlap_seconds": args.overlap_seconds,
        },
    )


def format_report(result: EngineResult) -> str:
    """Render the transcript with its timestamps and the measured run cost."""
    performance = result.metadata.get("performance")
    performance = performance if isinstance(performance, dict) else {}
    audio_seconds = performance.get("audio_seconds")
    audio_value = float(audio_seconds) if isinstance(audio_seconds, (int, float)) else None

    words = sum(len(segment.words) for segment in result.lyrics)
    engine_line = f"{result.engine} {result.engine_version or ''}".rstrip()
    lines = ["Lyrics", "======", f"File:     {result.audio_path}", f"Engine:   {engine_line}"]
    if audio_value is not None:
        lines.append(f"Duration: {audio_value:.3f} s")
    model = result.metadata.get("model")
    if isinstance(model, str):
        quantization = result.metadata.get("quantization")
        suffix = f" ({quantization})" if isinstance(quantization, str) else ""
        lines.append(f"Model:    {model}{suffix}")
    windows = result.metadata.get("windows")
    if isinstance(windows, int):
        with_text = result.metadata.get("windows_with_text")
        detail = f", {with_text} with text" if isinstance(with_text, int) else ""
        lines.append(f"Windows:  {windows}{detail}")
    lines.append(f"Segments: {len(result.lyrics)}")
    lines.append(f"Words:    {words}")

    for segment in result.lyrics:
        start = format_timestamp(segment.start) if segment.start is not None else "--:--"
        end = format_timestamp(segment.end) if segment.end is not None else "--:--"
        lines.append("")
        lines.append(f"[{start} - {end}] {segment.text}")
        for word in segment.words:
            word_start = format_timestamp(word.start) if word.start is not None else "--:--"
            word_end = format_timestamp(word.end) if word.end is not None else "--:--"
            lines.append(f"    {word_start} {word_end}  {word.text}")

    if not result.lyrics:
        lines.append("")
        lines.append("No text was transcribed from this file.")

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

    if result.warnings:
        lines.append("")
        lines.append("Warnings")
        lines.append("--------")
        lines.extend(f"  - {warning}" for warning in result.warnings)
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    """Execute ``songlab lyrics``."""
    options = _options(args)
    engine = resolve_engine(args.engine)
    if not engine.is_available():
        raise DependencyError(
            f"Engine {engine.name!r} is not available in this environment.",
            hint=(
                "Install the optional lyrics stack: pip install "
                '"song-chord-lyrics-analyzer[lyrics]" (onnx-asr, onnxruntime). '
                "'songlab doctor' lists the registered engines."
            ),
        )
    result = engine.transcribe(args.audio, options)
    if args.json:
        print(json.dumps(encode(result), indent=2, ensure_ascii=False))
        return 0
    print(format_report(result))
    return 0
