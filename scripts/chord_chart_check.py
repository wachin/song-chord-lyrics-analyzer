#!/usr/bin/env python3
"""Check a detected chord sequence against a hand-written chart.

This is developer tooling, not a shipped ``songlab`` command. It answers one
question a musician can actually ask of a real recording: *does the detector
find my chart's chords, in order?* It does not need timestamps in the chart and
does not invent them. See
:mod:`song_chord_lyrics_analyzer.evaluation.chart` for the format and the
semantics, and ``scripts/chord_benchmark.py`` for the timed GuitarSet benchmark.

Examples::

    # run the engine as the GUI would, then compare
    python scripts/chord_chart_check.py \\
        --chart "my song.txt" \\
        --audio "my song.mp3"

    # reuse a saved engine result instead of decoding again
    songlab chords "my song.mp3" --json > /tmp/chords.json
    python scripts/chord_chart_check.py \\
        --chart "my song.txt" --chords-json /tmp/chords.json

    # machine-readable report
    python scripts/chord_chart_check.py --chart chart.txt \\
        --audio song.mp3 --json

The chart is never committed here: it is the user's private reference. The
report's percentage is sequence agreement, not duration-weighted accuracy; an
abridged chart or a repeated section written only once will produce
missing/extra entries that are not detector mistakes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from song_chord_lyrics_analyzer.engines.base import ChordAnalysisOptions, EngineKind  # noqa: E402
from song_chord_lyrics_analyzer.engines.registry import create_default_registry  # noqa: E402
from song_chord_lyrics_analyzer.evaluation.chart import (  # noqa: E402
    Alignment,
    align_chord_sequences,
    parse_chord_chart,
)
from song_chord_lyrics_analyzer.utils.errors import SongLabError  # noqa: E402


def _detected_labels_from_document(document: Any) -> list[str]:
    """The labels of an engine result or a canonical analysis document."""
    if not isinstance(document, dict) or not isinstance(document.get("chords"), list):
        raise ValueError("the JSON document has no chords list")
    labels: list[str] = []
    for index, entry in enumerate(document["chords"]):
        if not isinstance(entry, dict) or not isinstance(entry.get("label"), str):
            raise ValueError(f"chord {index} has no string label")
        labels.append(entry["label"])
    return labels


def _detect(
    audio: Path, *, engine_name: str, minimum_duration: float | None
) -> tuple[list[str], str]:
    """Run the selected chord engine and return ``(labels, engine_version)``."""
    registry = create_default_registry()
    engine = registry.get(EngineKind.CHORDS, engine_name)
    if not engine.is_available():
        raise ValueError(
            f"engine {engine_name!r} is not available here; install the DSP extra "
            '(pip install -e ".[dev,dsp]")'
        )
    extra: dict[str, Any] = {}
    if minimum_duration is not None:
        extra["min_segment_seconds"] = minimum_duration
    result = engine.analyze(audio, ChordAnalysisOptions(extra=extra))
    return [event.label for event in result.chords], result.engine_version


def _report(
    chart_path: Path,
    chart,
    *,
    labels: list[str],
    engine_name: str,
    engine_version: str | None,
) -> str:
    alignment: Alignment = align_chord_sequences(chart.chords, labels)
    lines = [
        f"Chart:    {chart_path} ({len(chart.chords)} chords in {len(chart.chord_lines)} lines)",
        f"Detected: {len(labels)} chords"
        + (f" ({engine_name} {engine_version})" if engine_version else ""),
        f"Matched in order: {alignment.matches} / {alignment.chart_total} chart chords "
        f"({alignment.recall:.1%}) and {alignment.matches} / {alignment.detected_total} "
        f"detections ({alignment.precision:.1%})",
        f"Substitutions: {len(alignment.substitutions)}",
    ]
    for op in alignment.substitutions:
        lines.append(f"  chart {op.reference} -> detected {op.hypothesis}")
    if alignment.missing:
        lines.append(
            f"Missing from detection ({len(alignment.missing)}): {', '.join(alignment.missing)}"
        )
    else:
        lines.append("Missing from detection: none")
    if alignment.extra:
        lines.append(f"Extra detections ({len(alignment.extra)}): {', '.join(alignment.extra)}")
    else:
        lines.append("Extra detections: none")
    lines.append("")
    lines.append(
        "This is sequence agreement against a chart without timestamps, not "
        "duration-weighted accuracy. An abridged chart or a repeated section "
        "written only once will show missing/extra chords that are not detector errors."
    )
    return "\n".join(lines)


def _json_report(
    chart_path: Path, chart, alignment: Alignment, labels: list[str]
) -> dict[str, Any]:
    return {
        "chart": str(chart_path),
        "chart_chords": len(chart.chords),
        "chart_lines": len(chart.chord_lines),
        "sections": list(chart.sections),
        "detected_chords": len(labels),
        "matched": alignment.matches,
        "substitutions": len(alignment.substitutions),
        "missing": list(alignment.missing),
        "extra": list(alignment.extra),
        "recall": round(alignment.recall, 6),
        "precision": round(alignment.precision, 6),
        "score": alignment.score,
        "alignment": [
            {"chart": op.reference, "detected": op.hypothesis, "kind": op.kind}
            for op in alignment.ops
        ],
    }


def run(args: argparse.Namespace) -> int:
    """Parse the chart, obtain the detected labels and print the report."""
    chart = parse_chord_chart(args.chart.read_text(encoding="utf-8"), source=args.chart.name)
    if chart.is_empty:
        print(f"no chord line found in {args.chart}", file=sys.stderr)
        return 1
    engine_version: str | None = None
    if args.audio is not None:
        labels, engine_version = _detect(
            args.audio,
            engine_name=args.engine,
            minimum_duration=args.min_duration,
        )
    else:
        document = json.loads(args.chords_json.read_text(encoding="utf-8"))
        labels = _detected_labels_from_document(document)
    alignment = align_chord_sequences(chart.chords, labels)
    if args.json:
        print(json.dumps(_json_report(args.chart, chart, alignment, labels), indent=1))
    else:
        print(
            _report(
                args.chart,
                chart,
                labels=labels,
                engine_name=args.engine,
                engine_version=engine_version,
            )
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--chart", type=Path, required=True, help="plain-text chord chart")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--audio", type=Path, help="audio file to analyse now")
    source.add_argument(
        "--chords-json",
        type=Path,
        help="saved engine or analysis JSON with a chords list",
    )
    parser.add_argument("--engine", default="chroma-baseline", help="registered chord engine")
    parser.add_argument(
        "--min-duration",
        type=float,
        default=None,
        help="minimum chord seconds before merging (omit for the engine default; 0 disables)",
    )
    parser.add_argument("--json", action="store_true", help="print the full alignment as JSON")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (SongLabError, ValueError, json.JSONDecodeError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
