"""``songlab benchmark`` - score stored engine results (roadmap section 46).

Reads a directory of benchmark cases (a reference/hypothesis pair per song, see
``docs/BENCHMARK.md``), scores them with the roadmap section 44 metric family
and writes ``benchmark/{benchmark.json,benchmark.csv,benchmark.md}``. Cases
that declare an ``audio`` file can be (re)run through ``--engine NAME`` — of any
kind a metric family can score (chords, key, tempo, lyrics): the engine's
hypothesis and its measured section 45 run cost (processing time, peak memory)
fill the case before scoring, so nothing in the report is ever a number nobody
measured.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from song_chord_lyrics_analyzer.benchmark import (
    EngineRun,
    build_report,
    load_cases,
    run_engine_on_cases,
    write_reports,
)
from song_chord_lyrics_analyzer.engines import create_default_registry
from song_chord_lyrics_analyzer.performance import real_time_factor

__all__ = ["add_arguments", "format_run_notes", "format_summary", "run"]


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register ``songlab benchmark`` arguments."""
    parser.add_argument(
        "directory",
        type=Path,
        help="directory containing benchmark case JSON files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmark"),
        help="directory for benchmark.json/csv/md (default: ./benchmark)",
    )
    parser.add_argument(
        "--engine",
        metavar="NAME",
        default=None,
        help=(
            "run this engine (chords, key, tempo or lyrics) on every case that "
            "declares an 'audio' file before scoring (e.g. chroma-baseline)"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the report as JSON instead of writing the report files",
    )


def _format_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def format_summary(report: dict[str, Any], paths: Sequence[Path]) -> str:
    """Render a short human-readable summary of a benchmark report."""
    lines = [
        "Benchmark",
        "=========",
        f"Cases:   {len(report['cases'])}",
        f"Reports: {', '.join(str(path) for path in paths)}",
        "",
        "Engine summary (mean per engine)",
    ]
    for engine, values in sorted(report["summary"].items()):
        metrics = "  ".join(
            f"{key}={_format_value(value)}" for key, value in values.items() if key != "cases"
        )
        lines.append(f"  {engine}  cases={values['cases']}" + (f"  {metrics}" if metrics else ""))
    return "\n".join(lines)


def format_run_notes(engine_name: str, runs: Sequence[EngineRun]) -> list[str]:
    """Render one line per engine invocation, with the measured run cost."""
    lines = ["", "Engine runs", "-----------"]
    for run in runs:
        processing = (
            f"{run.processing_time_seconds:.3f} s"
            if run.processing_time_seconds is not None
            else "time not measured"
        )
        factor = real_time_factor(run.duration_seconds, run.processing_time_seconds)
        factor_note = f" (real-time factor {factor:.2f})" if factor is not None else ""
        lines.append(f"  {run.song}: {run.summary} in {processing}{factor_note}")
    lines.append(f"  engine: {engine_name}")
    return lines


def run(args: argparse.Namespace) -> int:
    """Execute ``songlab benchmark``."""
    cases = load_cases(args.directory)
    runs: list[EngineRun] = []
    engine_name = args.engine
    if engine_name is not None:
        engine = create_default_registry().find(engine_name)
        cases, runs = run_engine_on_cases(cases, engine)
    report = build_report(cases)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    if runs and engine_name is not None:
        print("\n".join(format_run_notes(engine_name, runs)))
    paths = write_reports(report, args.output)
    print(format_summary(report, paths))
    return 0
