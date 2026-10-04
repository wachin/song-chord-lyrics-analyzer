"""Benchmark scoring and reports (roadmap section 46).

Scores the stored reference/hypothesis pairs of a directory with the metric
family from :mod:`song_chord_lyrics_analyzer.metrics` (roadmap section 44) and
turns the result into ``benchmark.json``, ``benchmark.csv`` and
``benchmark.md``. No engine runs here and no number is invented: a metric is
reported only when both sides of a case actually provide what it needs.
"""

from __future__ import annotations

import csv
import io
import json
import math
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeGuard

from song_chord_lyrics_analyzer.benchmark.cases import BenchmarkCase
from song_chord_lyrics_analyzer.metrics import (
    character_error_rate,
    chord_change_detection,
    evaluate,
    key_relation,
    normalize_text,
    segment_overlap,
    tempo_error,
    tempo_interpretation,
    timing_error,
    weighted_key_score,
    word_error_rate,
    word_timestamp_error,
)
from song_chord_lyrics_analyzer.performance import real_time_factor

__all__ = [
    "CORE_COLUMNS",
    "NUMERIC_METRIC_KEYS",
    "TEXT_METRIC_KEYS",
    "build_report",
    "score_case",
    "to_csv",
    "to_json",
    "to_markdown",
    "write_reports",
]

#: Columns every row carries, before the metric columns.
CORE_COLUMNS = (
    "song",
    "engine",
    "engine_version",
    "model",
    "duration_seconds",
    "processing_time_seconds",
    "peak_memory_bytes",
)

#: Numeric metrics, in a fixed order so the CSV and Markdown tables are stable.
NUMERIC_METRIC_KEYS = (
    "lyrics.wer",
    "lyrics.cer",
    "lyrics.word_timestamp_median_seconds",
    "lyrics.word_timestamp_mean_seconds",
    "lyrics.word_timestamp_matched_words",
    "chords.exact_f1",
    "chords.root_f1",
    "chords.quality_f1",
    "chords.mirex_f1",
    "chords.multiset_f1",
    "chords.palette_f1",
    "chords.segment_overlap",
    "chords.change_detection.precision",
    "chords.change_detection.recall",
    "chords.change_detection.f1",
    "chords.timing_error_median_seconds",
    "key.weighted_score",
    "key.exact",
    "key.relative",
    "tempo.absolute_bpm_error",
    "tempo.half_tempo_error",
    "tempo.double_tempo_error",
    "performance.real_time_factor",
)

#: Textual metrics (a label, not a number), appended after the numeric ones.
TEXT_METRIC_KEYS = ("key.relation", "tempo.interpretation")


def _segments(raw: Any) -> list[tuple[float, float, str]]:
    if not isinstance(raw, list) or not raw:
        return []
    return [(float(item["start"]), float(item["end"]), str(item["label"])) for item in raw]


def _timed_words(raw: Any) -> list[tuple[str, float]]:
    if not isinstance(raw, list):
        return []
    return [
        (str(item["text"]), float(item["start"]))
        for item in raw
        if isinstance(item, dict) and "text" in item and "start" in item
    ]


def _is_number(value: Any) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _score_lyrics_text(
    reference: dict[str, Any], hypothesis: dict[str, Any], metrics: dict
) -> None:
    ref_text, hyp_text = reference.get("lyrics_text"), hypothesis.get("lyrics_text")
    if isinstance(ref_text, str) and isinstance(hyp_text, str) and normalize_text(ref_text):
        metrics["lyrics.wer"] = word_error_rate(ref_text, hyp_text)
        metrics["lyrics.cer"] = character_error_rate(ref_text, hyp_text)


def _score_lyrics_words(
    reference: dict[str, Any], hypothesis: dict[str, Any], metrics: dict
) -> None:
    ref_words, hyp_words = (
        _timed_words(reference.get("lyrics_words")),
        _timed_words(hypothesis.get("lyrics_words")),
    )
    if not ref_words or not hyp_words:
        return
    result = word_timestamp_error(ref_words, hyp_words)
    if not math.isnan(result["median_seconds"]):
        metrics["lyrics.word_timestamp_median_seconds"] = result["median_seconds"]
        metrics["lyrics.word_timestamp_mean_seconds"] = result["mean_seconds"]
    metrics["lyrics.word_timestamp_matched_words"] = result["matched_words"]


def _score_chords(reference: dict[str, Any], hypothesis: dict[str, Any], metrics: dict) -> None:
    ref_segments, hyp_segments = (
        _segments(reference.get("chords")),
        _segments(hypothesis.get("chords")),
    )
    if ref_segments and hyp_segments:
        metrics["chords.segment_overlap"] = segment_overlap(ref_segments, hyp_segments)
        detection = chord_change_detection(ref_segments, hyp_segments)
        metrics["chords.change_detection.precision"] = detection["precision"]
        metrics["chords.change_detection.recall"] = detection["recall"]
        metrics["chords.change_detection.f1"] = detection["f1"]
        timing = timing_error(ref_segments, hyp_segments)
        if not math.isnan(timing["reference_to_hypothesis"]):
            metrics["chords.timing_error_median_seconds"] = timing["reference_to_hypothesis"]


def _score_chord_labels(
    reference: dict[str, Any], hypothesis: dict[str, Any], metrics: dict
) -> None:
    ref_labels, hyp_labels = reference.get("chord_labels"), hypothesis.get("chord_labels")
    if not isinstance(ref_labels, list) or not isinstance(hyp_labels, list):
        return
    result = evaluate(ref_labels, hyp_labels)
    for view in ("exact", "root", "quality", "mirex"):
        view_result = result[view]
        assert isinstance(view_result, dict)  # evaluate always returns a PRF triple
        metrics[f"chords.{view}_f1"] = view_result["f1"]
    metrics["chords.multiset_f1"] = result["multiset_f1"]
    metrics["chords.palette_f1"] = result["palette_f1"]


def _score_key(reference: dict[str, Any], hypothesis: dict[str, Any], metrics: dict) -> None:
    ref_key, hyp_key = reference.get("key"), hypothesis.get("key")
    if not isinstance(ref_key, str) or not isinstance(hyp_key, str):
        return
    relation = key_relation(ref_key, hyp_key)
    metrics["key.relation"] = relation
    metrics["key.weighted_score"] = weighted_key_score(ref_key, hyp_key)
    metrics["key.exact"] = 1.0 if relation == "exact" else 0.0
    metrics["key.relative"] = 1.0 if relation == "relative" else 0.0


def _tempo_pair(
    reference: dict[str, Any], hypothesis: dict[str, Any]
) -> tuple[float, float] | None:
    ref_bpm, hyp_bpm = reference.get("tempo_bpm"), hypothesis.get("tempo_bpm")
    if not _is_number(ref_bpm) or not _is_number(hyp_bpm):
        return None
    if ref_bpm <= 0 or hyp_bpm <= 0:
        return None
    return float(ref_bpm), float(hyp_bpm)


def _score_tempo(reference: dict[str, Any], hypothesis: dict[str, Any], metrics: dict) -> None:
    pair = _tempo_pair(reference, hypothesis)
    if pair is None:
        return
    reference_bpm, estimated_bpm = pair
    for name, value in tempo_error(reference_bpm, estimated_bpm).items():
        metrics[f"tempo.{name}"] = value
    metrics["tempo.interpretation"] = tempo_interpretation(reference_bpm, estimated_bpm)


def _score_performance(case: BenchmarkCase, metrics: dict[str, Any]) -> None:
    """Report the section 45 real-time factor when the case recorded a run.

    Both numbers must be present: the audio duration and the measured
    processing time. A case that never recorded a run contributes no
    performance metric instead of a guessed one.
    """
    value = real_time_factor(case.duration_seconds, case.processing_time_seconds)
    if value is not None:
        metrics["performance.real_time_factor"] = value


def score_case(case: BenchmarkCase) -> dict[str, Any]:
    """Score one case into a report row with the metrics both sides support."""
    metrics: dict[str, Any] = {}
    _score_lyrics_text(case.reference, case.hypothesis, metrics)
    _score_lyrics_words(case.reference, case.hypothesis, metrics)
    _score_chords(case.reference, case.hypothesis, metrics)
    _score_chord_labels(case.reference, case.hypothesis, metrics)
    _score_key(case.reference, case.hypothesis, metrics)
    _score_tempo(case.reference, case.hypothesis, metrics)
    _score_performance(case, metrics)
    return {
        "song": case.song,
        "engine": case.engine,
        "engine_version": case.engine_version,
        "model": case.model,
        "duration_seconds": case.duration_seconds,
        "processing_time_seconds": case.processing_time_seconds,
        "peak_memory_bytes": case.peak_memory_bytes,
        "metrics": metrics,
    }


def _summarize(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Mean of every numeric metric per engine, plus the case count."""
    totals: dict[str, dict[str, float]] = {}
    counts: dict[str, dict[str, int]] = {}
    cases: dict[str, int] = {}
    for row in rows:
        engine = row["engine"] or "unknown"
        cases[engine] = cases.get(engine, 0) + 1
        for key, value in row["metrics"].items():
            if key in NUMERIC_METRIC_KEYS and _is_number(value):
                totals.setdefault(engine, {})[key] = (
                    totals.setdefault(engine, {}).get(key, 0.0) + value
                )
                counts.setdefault(engine, {})[key] = counts.setdefault(engine, {}).get(key, 0) + 1
    summary: dict[str, dict[str, Any]] = {}
    for engine, case_count in cases.items():
        engine_summary: dict[str, Any] = {"cases": case_count}
        for key, total in totals.get(engine, {}).items():
            engine_summary[key] = total / counts[engine][key]
        summary[engine] = engine_summary
    return summary


def build_report(cases: Sequence[BenchmarkCase]) -> dict[str, Any]:
    """Score every case and aggregate a per-engine summary."""
    rows = [score_case(case) for case in cases]
    return {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cases": rows,
        "summary": _summarize(rows),
    }


def _metric_columns() -> list[str]:
    return [*NUMERIC_METRIC_KEYS, *TEXT_METRIC_KEYS]


def _format_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def to_json(report: dict[str, Any]) -> str:
    """Serialize the report as pretty JSON."""
    return json.dumps(report, indent=2, ensure_ascii=False) + "\n"


def to_csv(report: dict[str, Any]) -> str:
    """Serialize the report as CSV, one row per case, one column per metric."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    columns = [*CORE_COLUMNS, *_metric_columns()]
    writer.writerow(columns)
    for row in report["cases"]:
        values = [_format_scalar(row.get(column)) for column in CORE_COLUMNS]
        values.extend(_format_scalar(row["metrics"].get(column)) for column in _metric_columns())
        writer.writerow(values)
    return buffer.getvalue()


def _markdown_table(header: Sequence[str], rows: Iterable[Sequence[str]]) -> list[str]:
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def to_markdown(report: dict[str, Any]) -> str:
    """Serialize the report as a readable Markdown document."""
    columns = _metric_columns()
    lines = [
        "# Benchmark",
        "",
        f"Generated: {report['generated']}",
        f"Cases: {len(report['cases'])}",
        "",
        "## Summary (mean per engine)",
        "",
    ]
    summary_rows = []
    for engine, values in sorted(report["summary"].items()):
        summary_rows.append(
            [
                engine,
                str(values["cases"]),
                *[_format_scalar(values.get(column)) for column in columns],
            ]
        )
    lines.extend(_markdown_table(["Engine", "Cases", *columns], summary_rows))

    lines.extend(["", "## Cases", ""])
    case_rows = []
    for row in report["cases"]:
        case_rows.append(
            [
                str(row["song"]),
                row["engine"] or "unknown",
                _format_scalar(row.get("duration_seconds")),
                *[_format_scalar(row["metrics"].get(column)) for column in columns],
            ]
        )
    lines.extend(_markdown_table(["Song", "Engine", "Duration (s)", *columns], case_rows))
    return "\n".join(lines) + "\n"


def write_reports(report: dict[str, Any], directory: Path) -> list[Path]:
    """Write ``benchmark.json``, ``benchmark.csv`` and ``benchmark.md``."""
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name, content in (
        ("benchmark.json", to_json(report)),
        ("benchmark.csv", to_csv(report)),
        ("benchmark.md", to_markdown(report)),
    ):
        path = directory / name
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written
