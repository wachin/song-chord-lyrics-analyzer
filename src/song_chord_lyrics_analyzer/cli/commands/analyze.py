"""``songlab analyze`` - run the whole pipeline on one audio file (roadmap 47).

The first command that produces the canonical document
:class:`~song_chord_lyrics_analyzer.models.analysis.AnalysisResult` instead of a
single engine's output. It holds no analysis logic: the pipeline lives in
:mod:`song_chord_lyrics_analyzer.analysis`, and this module only selects engines,
formats the outcome and offers the document as JSON.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from song_chord_lyrics_analyzer.analysis import SUPPORTED_KINDS, AnalysisOutcome, run_analysis
from song_chord_lyrics_analyzer.app.summary import lyrics_label
from song_chord_lyrics_analyzer.models.analysis import AnalysisResult
from song_chord_lyrics_analyzer.performance import real_time_factor
from song_chord_lyrics_analyzer.schema.codec import encode
from song_chord_lyrics_analyzer.utils.errors import InputError

__all__ = ["add_arguments", "format_report", "parse_engine_overrides", "run"]


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register ``songlab analyze`` arguments."""
    parser.add_argument("audio", type=Path, help="audio file to analyse")
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
        "--json",
        action="store_true",
        help="print the canonical analysis document as JSON",
    )
    parser.add_argument(
        "--no-hash",
        action="store_true",
        help="skip the SHA-256 of the input in provenance (faster on large files)",
    )


def parse_engine_overrides(values: Sequence[str] | None) -> dict[str, str]:
    """Parse ``KIND=NAME`` overrides into a mapping for the analysis service.

    Raises:
        InputError: When an entry is malformed or names a layer this pipeline
            does not run.
    """
    if not values:
        return {}
    supported = ", ".join(kind.value for kind in SUPPORTED_KINDS)
    overrides: dict[str, str] = {}
    for entry in values:
        kind, separator, name = entry.partition("=")
        kind = kind.strip()
        if not separator or not name.strip():
            raise InputError(
                f"Invalid --engine value: {entry!r}",
                hint=(
                    "Use --engine KIND=NAME, for example "
                    f"--engine chords=chroma-baseline. Layers: {supported}."
                ),
            )
        if kind not in {supported_kind.value for supported_kind in SUPPORTED_KINDS}:
            raise InputError(
                f"Unknown analysis layer: {kind!r}",
                hint=f"Supported layers: {supported}.",
            )
        overrides[kind] = name.strip()
    return overrides


def _format_confidence(document: AnalysisResult) -> str:
    """The key's confidence, or an honest "unknown" when the engine gave none."""
    if document.key is None:
        return "unknown"
    return str(document.key.confidence)


def format_report(outcome: AnalysisOutcome) -> str:
    """Render the analysis as a readable report with its provenance."""
    document = outcome.result
    audio = document.audio
    lines = [
        "Analysis",
        "========",
        f"File:     {audio.path if audio is not None else 'unknown'}",
    ]
    if audio is not None:
        lines.append(
            f"Duration: {audio.duration_label}"
            + (f" ({audio.duration:.3f} s)" if audio.duration is not None else "")
        )
    lines.append(f"Status:   {document.run.status.value}")

    lines.extend(["", "Steps", "-----"])
    for step in outcome.steps:
        cost = (
            f" in {step.processing_time_seconds:.3f} s"
            if step.processing_time_seconds is not None
            else ""
        )
        lines.append(
            f"  {step.kind:<8} {step.engine:<18} {step.status.value:<9} {step.detail or ''}{cost}"
        )

    lines.extend(["", "Results", "-------"])
    lines.append(f"  Chords: {len(document.chords)}")
    lyrics = lyrics_label(document)
    if lyrics is not None:
        lines.append(f"  Lyrics: {lyrics}")
    lines.append(
        f"  Key:    {document.key.label if document.key is not None else 'unknown'}"
        f"  (confidence {_format_confidence(document)})"
    )
    if document.tempo is not None:
        alternatives = ", ".join(f"{value:.1f}" for value in document.tempo.alternatives)
        lines.append(
            f"  Tempo:  {document.tempo.bpm:.1f} BPM  (half/double readings: {alternatives})"
        )
    else:
        lines.append("  Tempo:  unknown")

    total = outcome.total_processing_seconds
    if total is not None:
        factor_note = ""
        if audio is not None and audio.duration is not None:
            factor = real_time_factor(audio.duration, total)
            factor_note = f" (real-time factor {factor:.2f})" if factor is not None else ""
        lines.append("")
        lines.append(f"Total processing: {total:.3f} s{factor_note}")

    provenance = document.provenance
    lines.extend(["", "Provenance", "----------"])
    engines = ", ".join(sorted(provenance.engines)) or "none"
    lines.append(
        f"  {provenance.application_version} | {provenance.python_version} | {provenance.platform}"
    )
    lines.append(f"  engines: {engines}")
    if provenance.input_hash:
        lines.append(f"  sha256:  {provenance.input_hash}")

    if document.warnings:
        lines.extend(["", "Warnings", "--------"])
        lines.extend(f"  - {warning}" for warning in document.warnings)
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    """Execute ``songlab analyze``."""
    outcome = run_analysis(
        args.audio,
        engines=parse_engine_overrides(args.engine),
        input_hash=not args.no_hash,
    )
    if args.json:
        print(json.dumps(encode(outcome.result), indent=2, ensure_ascii=False))
        return 0
    print(format_report(outcome))
    return 0
