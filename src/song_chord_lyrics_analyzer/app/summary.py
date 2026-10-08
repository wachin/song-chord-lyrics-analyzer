"""Describe one analysis as label/value rows a front end can show (Phase D).

Roadmap Phase D asks the minimal window to show "key, tempo, engine name and
provenance summary (cheap, already available)". Running those on the analysis
document is presenter work, not widget work: a widget that formats strings is a
widget that cannot be tested without a display.

:func:`summarize` is therefore a pure function from the canonical document (plus
the per-step run summary the analysis service already returns) to an ordered
sequence of :class:`SummaryRow`. The window puts them in a form layout, a
terminal could print them, and the tests assert the strings directly.

A row is omitted when the document genuinely has no value for it. Missing
evidence is never reported as a number or as "0", the same rule the analysis
service follows.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from song_chord_lyrics_analyzer.analysis.service import StepOutcome, StepStatus
from song_chord_lyrics_analyzer.models.analysis import AnalysisResult
from song_chord_lyrics_analyzer.utils.time import format_timestamp

__all__ = [
    "SummaryRow",
    "summarize",
]

#: How much of the input SHA-256 to show: enough to compare two runs by eye.
_HASH_PREFIX = 12


@dataclass(frozen=True)
class SummaryRow:
    """One ``label: value`` pair of an analysis summary.

    Attributes:
        label: Short field name, e.g. ``"Key"``.
        value: The value to show, already formatted.
    """

    label: str
    value: str


def _describe_engines(document: AnalysisResult, steps: Sequence[StepOutcome]) -> str | None:
    """Which engine ran for which layer, preferring the run's own record."""
    if steps:
        parts = [f"{step.kind}={step.engine}" for step in steps if step.status is StepStatus.OK]
        if parts:
            return ", ".join(parts)
    configuration = document.provenance.configuration
    if not configuration:
        return None
    return ", ".join(f"{kind}={name}" for kind, name in sorted(configuration.items()))


def _describe_tempo(document: AnalysisResult) -> str | None:
    """BPM, with the competing interpretations the engine kept."""
    tempo = document.tempo
    if tempo is None:
        return None
    text = f"{tempo.bpm:.1f} BPM"
    if tempo.is_ambiguous:
        alternatives = ", ".join(f"{bpm:.1f}" for bpm in tempo.alternatives)
        text = f"{text} (also {alternatives} BPM)"
    if tempo.meter:
        text = f"{text} in {tempo.meter}"
    return text


def _describe_chords(document: AnalysisResult) -> str:
    """How many chord events were detected, and what to look at if none were."""
    count = len(document.chords)
    if count == 0:
        return "none detected"
    sources = sorted({event.source for event in document.chords if event.source})
    suffix = f" from {', '.join(sources)}" if sources else ""
    return f"{count} events{suffix}"


def summarize(
    document: AnalysisResult,
    *,
    steps: Sequence[StepOutcome] = (),
) -> tuple[SummaryRow, ...]:
    """Describe ``document`` as the rows of an analysis panel.

    Args:
        document: The canonical document of an analysis.
        steps: The per-engine steps of the run, when the caller has them; they
            are what tells an unavailable engine apart from an engine that
            produced nothing.

    Returns:
        The rows to show, in reading order. Rows the document has no value for
        are absent.
    """
    provenance = document.provenance
    rows: list[SummaryRow] = []

    audio = document.audio
    if audio is not None:
        rows.append(SummaryRow("File", audio.path.name))
        if audio.duration:
            rows.append(SummaryRow("Duration", format_timestamp(float(audio.duration))))
    rows.append(SummaryRow("Chords", _describe_chords(document)))
    rows.append(SummaryRow("Key", document.key.label if document.key is not None else "unknown"))

    tempo = _describe_tempo(document)
    if tempo is not None:
        rows.append(SummaryRow("Tempo", tempo))

    engines = _describe_engines(document, steps)
    if engines is not None:
        rows.append(SummaryRow("Engines", engines))

    for step in steps:
        if step.status is StepStatus.OK:
            continue
        detail = step.detail or step.status.value
        rows.append(
            SummaryRow(step.status.value.capitalize(), f"{step.kind} ({step.engine}): {detail}")
        )

    rows.append(SummaryRow("Run", document.run.status.value))
    rows.append(SummaryRow("Application", provenance.application_version))
    if provenance.python_version:
        rows.append(SummaryRow("Python", provenance.python_version))
    if provenance.platform:
        rows.append(SummaryRow("Platform", provenance.platform))
    if provenance.input_hash:
        rows.append(SummaryRow("Input SHA-256", f"{provenance.input_hash[:_HASH_PREFIX]}..."))
    if document.warnings:
        rows.append(SummaryRow("Warnings", str(len(document.warnings))))
    return tuple(rows)
