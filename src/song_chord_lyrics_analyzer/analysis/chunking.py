"""Windowed chord analysis for long audio (roadmap Phase K).

Why this exists, measured rather than assumed: the chord engine decodes the
audio it analyses and builds a chroma matrix over it, so a whole-file pass holds
both at once. On a three-hour concert recording that is hundreds of megabytes of
samples plus its chroma, and the run becomes an out-of-memory risk rather than a
slow analysis. Windowing bounds both, at the price of a seam where two windows
meet - so the seam rules below are the whole point of this module.

The rules, all deterministic and none of them a guess:

* **One notion of a window.** Windows come from
  :func:`~song_chord_lyrics_analyzer.engines.lyrics_chunking.plan_chunks`, the
  planner the lyrics engine already uses, so "a 120 s window" means the same
  thing in both layers and the tiling rules (the last window is shortened, a
  window that repeats covered audio is not planned) are not written twice.
* **The engine's time range contract is relied on, not assumed.** An engine is
  called once per window with ``ChordAnalysisOptions(start=..., end=...)``, and
  the contract is that it returns events on the *file's* timeline (the chroma
  baseline decodes with ``offset`` and shifts by it). A window whose events
  start before the window itself therefore proves the engine ignored the range:
  that is reported as an :class:`InputError`, never concatenated into a
  duplicated timeline.
* **An earlier window wins, and coverage is never lost.** When windows
  overlap, an event that starts inside coverage a previous window already
  reported keeps only its part *after* that coverage, and an event that lies
  entirely inside it is dropped: the first window heard that audio first, and
  the cut is made at a time already known (where the earlier coverage ended),
  so no boundary is invented. The lyrics reassembly states the same rule but
  drops the whole event, which is why a word clipped at a window edge can be
  lost there; here the interval is kept, because a chord *is* an interval.
* **The seam is repaired, not smoothed.** When the first event of a window
  repeats the label the previous window ended on and starts no later than one
  frame after that event ended, the two halves become one event. The bound is
  :data:`SEAM_TOLERANCE_SECONDS` and it applies *only* across a window boundary,
  never inside one: a chord split by the windowing is an artifact of this
  module, while two short same-label chords inside one window are what the
  engine actually reported.

Nothing here invents a chord, a boundary or a confidence: the merged
confidence is the windows' own value only when every window agreed, and
``raw`` payloads are dropped because per-window payloads are not one payload.

What windowing can still cost, measured on a 480 s tonal fixture at a 60 s
window (see ``docs/ENGINE_COMPARISON.md``): all sixty chord labels and their
order were identical to the whole-file pass, and one boundary of sixty moved
by 94 ms - exactly at a seam, because a change inside a window's first frame is
attributed to the window's own start. That is the reason this stays opt-in:
the whole-file pass is what the recorded accuracy numbers were measured with.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from song_chord_lyrics_analyzer.engines.base import ChordAnalysisOptions
from song_chord_lyrics_analyzer.engines.lyrics_chunking import Chunk, plan_chunks
from song_chord_lyrics_analyzer.models.analysis import EngineResult
from song_chord_lyrics_analyzer.models.confidence import ConfidenceScore
from song_chord_lyrics_analyzer.models.music import ChordEvent
from song_chord_lyrics_analyzer.utils.errors import InputError

__all__ = [
    "DEFAULT_CHORD_CHUNK_SECONDS",
    "SEAM_TOLERANCE_SECONDS",
    "analyze_chords_in_windows",
    "merge_window_results",
]

#: Window length used when a caller asks for windowed chord analysis without
#: naming one. Two minutes keeps a window's chroma well inside a few MB while
#: staying long enough that a song has few seams.
DEFAULT_CHORD_CHUNK_SECONDS = 120.0

#: How far apart two same-label events may be and still count as the two halves
#: of one chord split by a window boundary. One analysis frame is ~23 ms at the
#: shared decoder's hop (*512 / 22 050 Hz*); 50 ms is the documented bound.
SEAM_TOLERANCE_SECONDS = 0.05

#: Float noise tolerated when asking whether an engine respected a window start.
_START_TOLERANCE_SECONDS = 1e-6

#: How a caller is told a window finished: ``(index, total, chunk)``, 1-based.
WindowObserver = Callable[[int, int, "Chunk"], None]


def _reject_ignored_range(chunk: Chunk, result: EngineResult) -> None:
    """Report an engine that returned events before the window it was given.

    Raises:
        InputError: When an event starts before the window does, which means the
            engine did not honour ``start`` and its output is on a local clock.
    """
    for event in result.chords:
        if event.start < chunk.start - _START_TOLERANCE_SECONDS:
            raise InputError(
                f"Engine {result.engine!r} returned an event at {event.start:.3f} s "
                f"for the window starting at {chunk.start:.3f} s.",
                hint=(
                    "A windowed run needs an engine that honours "
                    "ChordAnalysisOptions.start/end and returns events on the "
                    "file's timeline; run without windowing for this engine."
                ),
            )


def _uncovered_part(event: ChordEvent, frontier: float | None) -> ChordEvent | None:
    """The part of ``event`` a previous window has not already reported.

    Returns ``None`` when the whole event lies inside the coverage (a second
    look at audio an earlier window heard first), the event itself when it
    starts at or after the coverage, and the event clipped to the coverage's end
    when it straddles it - the only boundary involved is the one the earlier
    window already established.
    """
    if frontier is None or event.start >= frontier:
        return event
    if event.end is None or event.end <= frontier:
        return None
    return replace(event, start=frontier)


def _window_end(events: Sequence[ChordEvent]) -> float | None:
    """Where the audio covered by one window's output ends, when it says so."""
    ends = [event.end for event in events if event.end is not None]
    return max(ends) if ends else None


def _is_seam_continuation(previous: ChordEvent, following: ChordEvent) -> bool:
    """Whether ``following`` is the second half of ``previous``, split by a seam."""
    if previous.end is None or following.end is None:
        return False
    if previous.label != following.label or previous.source != following.source:
        return False
    return previous.end <= following.start <= previous.end + SEAM_TOLERANCE_SECONDS


def _same_confidence(results: Sequence[EngineResult]) -> ConfidenceScore:
    """The confidence every window agreed on, or ``unknown`` when they differ.

    A windowed run has no single engine measurement, so a disagreement is
    reported as unknown instead of one window's number standing in for the song.
    """
    first = results[0].confidence
    if all(result.confidence == first for result in results[1:]):
        return first
    return ConfidenceScore.unknown()


def _total_processing_time(results: Sequence[EngineResult]) -> float | None:
    """Sum of the windows' measured run times, or ``None`` when any is unmetered."""
    times = [result.processing_time_seconds for result in results]
    if any(time is None for time in times):
        return None
    return sum(time for time in times if time is not None)


def _metadata(
    results: Sequence[EngineResult], chunks: Sequence[Chunk], overlap: float
) -> dict[str, Any]:
    """The merged result's metadata: the windows' own facts plus the tiling."""
    metadata: dict[str, Any] = dict(results[0].metadata)
    metadata["windows"] = len(chunks)
    metadata["chunk_seconds"] = chunks[0].duration if chunks else 0.0
    metadata["overlap_seconds"] = overlap
    performance = metadata.get("performance")
    if isinstance(performance, dict):
        merged = dict(performance)
        merged["processing_time_seconds"] = _total_processing_time(results)
        window_seconds: list[float] = []
        for result in results:
            one = result.metadata.get("performance")
            value = one.get("audio_seconds") if isinstance(one, dict) else None
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                window_seconds.append(float(value))
        if len(window_seconds) == len(results):  # every window measured its audio
            merged["audio_seconds"] = sum(window_seconds)
        metadata["performance"] = merged
    return metadata


def merge_window_results(
    chunks: Sequence[Chunk],
    results: Sequence[EngineResult],
    *,
    overlap_seconds: float = 0.0,
) -> EngineResult:
    """Join per-window chord results into one result on the file's timeline.

    Args:
        chunks: The windows that were analysed, in playback order.
        results: One result per window, in the same order. Events are expected
            to be on the file's timeline already (the engine's ``start``/``end``
            contract).
        overlap_seconds: How much the windows shared, recorded in metadata.

    Returns:
        One :class:`EngineResult` whose chords are in playback order, with
        seam duplicates dropped and seam-split chords joined.

    Raises:
        ValueError: When the two sequences do not line up one to one.
    """
    if len(results) != len(chunks):
        raise ValueError(f"got {len(results)} chord results for {len(chunks)} windows")
    events: list[ChordEvent] = []
    frontier: float | None = None
    warnings: list[str] = []
    for _chunk, result in zip(chunks, results, strict=True):
        window_events = list(result.chords)
        kept = [
            part
            for part in (_uncovered_part(event, frontier) for event in window_events)
            if part is not None
        ]
        if kept and events and _is_seam_continuation(events[-1], kept[0]):
            # Two halves of one chord: the earlier event keeps its start and
            # takes the later end, so coverage crosses the seam without a gap.
            events[-1] = replace(events[-1], end=kept[0].end)
            kept = kept[1:]
        events.extend(kept)
        window_end = _window_end(window_events)
        if window_end is not None:
            frontier = window_end if frontier is None else max(frontier, window_end)
        for warning in result.warnings:
            if warning not in warnings:
                warnings.append(warning)

    template = results[0]
    return EngineResult(
        engine=template.engine,
        kind=template.kind,
        engine_version=template.engine_version,
        audio_path=template.audio_path,
        chords=events,
        confidence=_same_confidence(results),
        processing_time_seconds=_total_processing_time(results),
        raw=None,  # per-window payloads are not one payload; nothing is faked up
        warnings=warnings,
        metadata=_metadata(results, chunks, overlap_seconds),
    )


def analyze_chords_in_windows(
    engine: Any,
    audio_path: str | Path,
    *,
    duration: float | None,
    chunk_seconds: float = DEFAULT_CHORD_CHUNK_SECONDS,
    overlap_seconds: float = 0.0,
    options: ChordAnalysisOptions | None = None,
    on_window: WindowObserver | None = None,
) -> EngineResult:
    """Analyse ``audio_path`` in windows with ``engine`` and merge the results.

    Args:
        engine: A ``ChordEngine``.
        audio_path: The recording to analyse.
        duration: Length of the recording in seconds, as the audio probe
            measured it. ``None`` (or ``0``) means the audio cannot be tiled:
            the engine is then called once, whole-file, exactly as without this
            module - a window plan is never invented from an unknown length.
        chunk_seconds: Window length; defaults to
            :data:`DEFAULT_CHORD_CHUNK_SECONDS`.
        overlap_seconds: How much neighbouring windows share. ``0`` tiles the
            audio exactly, which is what the seam rules assume.
        options: Engine options to pass through; ``start``/``end`` are set per
            window and therefore ignored when given.
        on_window: Called after each window with ``(index, total, chunk)``,
            counting from 1, so a front end can report progress.

    Returns:
        One :class:`EngineResult` for the whole recording.

    Raises:
        InputError: When the tiling options are impossible, when the audio is
            too short to window meaningfully, or when the engine ignored the
            time range it was given (see the module docstring).
    """
    path = Path(audio_path)
    base = options if options is not None else ChordAnalysisOptions()
    if duration is None or duration <= 0.0:
        return engine.analyze(path, base)
    chunks = plan_chunks(duration, chunk_seconds=chunk_seconds, overlap_seconds=overlap_seconds)
    if len(chunks) < 2:
        # A single window is not a windowed analysis: the whole-file call keeps
        # the engine's own one-pass behaviour (and its raw payload).
        return engine.analyze(path, base)
    results: list[EngineResult] = []
    for index, chunk in enumerate(chunks, start=1):
        result = engine.analyze(path, replace(base, start=chunk.start, end=chunk.end))
        _reject_ignored_range(chunk, result)
        results.append(result)
        if on_window is not None:
            on_window(index, len(chunks), chunk)
    return merge_window_results(chunks, results, overlap_seconds=overlap_seconds)
