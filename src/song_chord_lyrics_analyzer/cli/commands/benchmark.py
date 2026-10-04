"""``songlab benchmark`` - score stored engine results (roadmap section 46).

Reads a directory of benchmark cases (a reference/hypothesis pair per song, see
``docs/BENCHMARK.md``), scores them with the roadmap section 44 metric family
and writes ``benchmark/{benchmark.json,benchmark.csv,benchmark.md}``. No engine
runs here: this command wires the metrics into a per-engine report over results
that were already produced.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from song_chord_lyrics_analyzer.benchmark import build_report, load_cases, write_reports

__all__ = ["add_arguments", "format_summary", "run"]


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


def run(args: argparse.Namespace) -> int:
    """Execute ``songlab benchmark``."""
    cases = load_cases(args.directory)
    report = build_report(cases)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    paths = write_reports(report, args.output)
    print(format_summary(report, paths))
    return 0
