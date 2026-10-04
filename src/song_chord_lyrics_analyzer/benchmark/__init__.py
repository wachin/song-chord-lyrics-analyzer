"""Benchmark package (roadmap section 46).

Scores stored reference/hypothesis pairs with the roadmap section 44 metric
family and writes ``benchmark.json``, ``benchmark.csv`` and ``benchmark.md``.
No engine runs here; the command wires the metrics into a per-engine report.
"""

from __future__ import annotations

from song_chord_lyrics_analyzer.benchmark.cases import BenchmarkCase, load_case, load_cases
from song_chord_lyrics_analyzer.benchmark.report import (
    build_report,
    score_case,
    to_csv,
    to_json,
    to_markdown,
    write_reports,
)

__all__ = [
    "BenchmarkCase",
    "build_report",
    "load_case",
    "load_cases",
    "score_case",
    "to_csv",
    "to_json",
    "to_markdown",
    "write_reports",
]
