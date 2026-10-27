"""Chroma template baseline chord engine (roadmap sections 13, 14, 18, 19 and 59).

The first concrete engine behind the
:class:`~song_chord_lyrics_analyzer.engines.base.ChordEngine` protocol. It is
deliberately simple and fully inspectable:

1. decode the audio to mono 22.05 kHz through the shared decode service
   (:func:`~song_chord_lyrics_analyzer.audio.decode.decode_audio`);
2. compute per-frame CQT chroma (optionally HPSS-harmonic, tuning-corrected,
   CENS or energy-gated — one variable at a time, see
   :func:`front_end_settings`);
3. match every frame against the 24 phase-1 triad templates (12 major, 12
   minor) by cosine similarity, reporting ``N`` when no template fits;
4. decode the frame scores into a label sequence — either a majority filter
   (roadmap section 19) or a max-sum Viterbi over a flat change penalty
   (roadmap section 20; the default, selectable through ``options.extra``);
5. collapse runs of equal labels into timed :class:`ChordEvent` segments;
6. measure each segment's score margin (its own state against the best
   competing state on the segment's frames) and report it as the event's
   confidence through a logistic calibrated on GuitarSet
   (:data:`CONFIDENCE_SLOPE`, :func:`margin_confidence`).

The DSP front end (numpy + librosa) is **optional**: :meth:`ChromaBaselineEngine.is_available`
reports whether it is importable, and :meth:`ChromaBaselineEngine.analyze` raises
:class:`~song_chord_lyrics_analyzer.utils.errors.DependencyError` with an
install hint instead of failing obscurely. Steps 3-6 are dependency-free
functions so they can be tested without the DSP stack.

Every number the run produces — processing time, audio duration, peak RSS, the
real-time factor — is measured by :mod:`song_chord_lyrics_analyzer.performance`
(roadmap section 45) on the machine doing the work. Nothing is estimated.
"""

from __future__ import annotations

import importlib
import math
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from song_chord_lyrics_analyzer.audio.decode import decode_audio
from song_chord_lyrics_analyzer.engines.base import (
    DEFAULT_MINIMUM_CHORD_DURATION,
    ChordAnalysisOptions,
    EngineKind,
)
from song_chord_lyrics_analyzer.engines.decoding import viterbi_decode
from song_chord_lyrics_analyzer.models.analysis import EngineInfo, EngineResult
from song_chord_lyrics_analyzer.models.confidence import ConfidenceScore
from song_chord_lyrics_analyzer.models.music import PITCH_CLASS_NAMES, ChordEvent, ChordQuality
from song_chord_lyrics_analyzer.performance import PerformanceProbe
from song_chord_lyrics_analyzer.utils.errors import (
    AudioFileNotFoundError,
    DependencyError,
    InputError,
)

__all__ = [
    "CONFIDENCE_INTERCEPT",
    "CONFIDENCE_SLOPE",
    "DEFAULT_CHANGE_PENALTY",
    "DEFAULT_ENERGY_GATE_DB",
    "DEFAULT_FEATURE",
    "DEFAULT_FEATURE_TRANSFORM",
    "DEFAULT_HARMONIC",
    "DEFAULT_MIN_SEGMENT_SECONDS",
    "DEFAULT_TEMPLATE_WEIGHTING",
    "DEFAULT_TUNING",
    "DEFAULT_DECODER",
    "DEFAULT_MATCH_THRESHOLD",
    "DEFAULT_NO_CHORD_SCORE",
    "DEFAULT_SMOOTHING_WINDOW",
    "ENGINE_NAME",
    "ENGINE_VERSION",
    "HOP_LENGTH",
    "SAMPLE_RATE",
    "SUPPORTED_FEATURES",
    "SUPPORTED_FEATURE_TRANSFORMS",
    "SUPPORTED_TEMPLATE_WEIGHTINGS",
    "SUPPORTED_TUNING",
    "TEMPLATE_LABELS",
    "HARMONIC_TEMPLATES",
    "ChromaBaselineEngine",
    "FrontEndSettings",
    "apply_feature_transform",
    "compute_chroma",
    "feature_transform",
    "front_end_settings",
    "decode_labels",
    "events_from_segments",
    "frame_scores",
    "margin_confidence",
    "match_frames",
    "merge_short_segments",
    "segment_margins",
    "segments_from_labels",
    "smooth_labels",
    "template_weighting",
]

#: Stable, CLI-facing engine identifier.
ENGINE_NAME = "chroma-baseline"
#: Engine version recorded as provenance in every result.
ENGINE_VERSION = "0.2.0"

#: Audio decoded to this mono sample rate before analysis.
SAMPLE_RATE = 22_050
#: Chroma frame hop in samples (~93 ms, ~10.7 frames per second).
HOP_LENGTH = 2_048

#: Cosine similarity a frame needs to be reported as a chord instead of ``N``.
#: Frames below it are honest no-chord readings, not forced matches.
DEFAULT_MATCH_THRESHOLD = 0.5
#: Majority-filter window (in frames) that removes isolated label flips.
DEFAULT_SMOOTHING_WINDOW = 5

#: Chroma feature used by the front end: ``"cqt"`` (the default, and the one the
#: confidence mapping is calibrated on) or ``"cens"`` (chroma energy normalised
#: statistics, which smooths over time).
DEFAULT_FEATURE = "cqt"
#: Tuning handling. ``"zero"`` (the default) assumes A440 equal temperament
#: and corrects for nothing; ``"auto"`` lets librosa estimate the deviation
#: inside ``cqt()`` (that is what every earlier measurement used);
#: ``"estimate"`` measures the deviation here (``librosa.estimate_tuning``),
#: records it in cents and passes it to the CQT explicitly.
#:
#: ``auto`` and ``zero`` are **not** the same call: in librosa 1.0,
#: ``chroma_cqt(tuning=None)`` estimates the tuning from the signal, while
#: ``tuning=0.0`` disables that correction. The default was moved from ``auto``
#: to ``zero`` on 2026-10-20 after a one-variable-at-a-time measurement on the
#: 180 GuitarSet comping takes: ``zero`` gained +0.0092 duration CSR against
#: the instructed lead sheet and +0.0064 against the performed voicings, with
#: no regression in change F1 or boundary error and slightly less CPU.
#: GuitarSet is played in tune, so this is a measured win on that corpus, not a
#: claim about detuned recordings; ``auto`` stays one flag away and
#: ``docs/ENGINE_COMPARISON.md`` §7 carries the table.
DEFAULT_TUNING = "zero"
#: Whether to analyse the harmonic component of an HPSS split instead of the mix.
DEFAULT_HARMONIC = False
#: Frame energy gate in dB relative to the loudest frame. ``0.0`` disables it; a
#: negative value zeros the chroma of frames below it, so those frames can only
#: be decoded as ``N``.
DEFAULT_ENERGY_GATE_DB = 0.0

#: Accepted feature and tuning values, validated with an install-free message.
SUPPORTED_FEATURES: tuple[str, ...] = ("cqt", "cens")
SUPPORTED_TUNING: tuple[str, ...] = ("zero", "auto", "estimate")

#: Per-frame compression applied to the chroma before template matching.
#: ``"sqrt"`` is the measured default (2026-10-21): it reduced the influence of
#: one loud overtone on a 12-bin vector and gained +0.0044 duration CSR over the
#: raw chroma on the 180 GuitarSet comping takes, with the harmonic templates
#: below and the same decoder. ``"raw"`` keeps the previous behaviour and
#: ``"log"`` compresses harder.
DEFAULT_FEATURE_TRANSFORM = "sqrt"
SUPPORTED_FEATURE_TRANSFORMS: tuple[str, ...] = ("raw", "sqrt", "log")

#: Template weighting used by the engine. ``"harmonic"`` (the default) weights
#: the root/third/fifth 1.00/0.95/0.85 and pushes the clashing third of the
#: opposite quality negative, which measurably beat the flat binary triads of
#: ``"binary"`` on the 180 GuitarSet comping takes (see
#: ``docs/ENGINE_COMPARISON.md`` §8). The binary set stays the library default
#: of :func:`frame_scores`/:func:`match_frames` so every earlier pinned test
#: keeps describing the earlier geometry.
DEFAULT_TEMPLATE_WEIGHTING = "harmonic"
SUPPORTED_TEMPLATE_WEIGHTINGS: tuple[str, ...] = ("binary", "harmonic")

#: Segments shorter than this are merged into a neighbour before the events are
#: emitted. The public default lives in
#: :data:`~song_chord_lyrics_analyzer.engines.base.DEFAULT_MINIMUM_CHORD_DURATION`
#: because it is a product default shared by the CLI and the session; an engine
#: caller can override it with ``extra["min_segment_seconds"]`` (0 disables).
DEFAULT_MIN_SEGMENT_SECONDS = DEFAULT_MINIMUM_CHORD_DURATION

#: CQT bins per octave. ``cqt(tuning=...)`` expects fractions of one of these
#: bins, while :func:`librosa.estimate_tuning` returns fractions of a semitone,
#: so an estimate is scaled by ``CQT_BINS_PER_OCTAVE / 12`` before use.
CQT_BINS_PER_OCTAVE = 36

#: Temporal decoder: ``"majority"`` (per-frame argmax + majority smoother,
#: roadmap section 19) or ``"viterbi"`` (max-sum sequence decoding, roadmap
#: section 20).
DEFAULT_DECODER = "viterbi"
#: Flat transition cost per chord change for the Viterbi decoder. ``0.0``
#: decodes every frame independently. The default is the measured optimum for
#: the current front end (``sqrt`` chroma + harmonic templates): 180 GuitarSet
#: comping takes, 2026-10-21. The previous front end measured 0.80; the number
#: follows the emissions, which is exactly why it is re-measured with them.
DEFAULT_CHANGE_PENALTY = 0.40
#: Emission score of the Viterbi no-chord state. It is a constant, so a frame
#: is decoded as ``N`` only when no triad outscores it by enough *and* the
#: change costs the transition penalty.
DEFAULT_NO_CHORD_SCORE = 0.06

#: Slope and intercept of the logistic that turns an event's mean score margin
#: (:func:`segment_margins`) into the confidence reported on every event.
#:
#: The value it produces is a **calibrated probability that the event's label is
#: right at that instant**, and only on the corpus it was fitted to: the 90
#: even-indexed GuitarSet comping takes of
#: ``tests/fixtures/guitarset_comp_manifest.json``, against the instructed JAMS
#: annotation, with the current front end (``feature_transform="sqrt"``,
#: ``template_weighting="harmonic"``, ``tuning="zero"``), a 0.50 s minimum
#: segment, the Viterbi decoder and the 0.40 change penalty. It was refitted on
#: 2026-10-27 (Linux, CPython 3.13.5, numpy 2.5.3, librosa 1.0.0) after the
#: minimum-duration default moved to 0.50 s and measured on the 90 held-out
#: odd-indexed takes: Brier score 0.1485, expected calibration error 0.0363, and
#: accuracy 0.809 on the events scoring at least 0.60 (47.6 % of the held-out
#: duration). GuitarSet is solo acoustic guitar, so elsewhere the number is a
#: heuristic, not a guarantee.
#:
#: The constants follow the front end: every front-end or template change moves
#: the margin scale, so the logistic is refitted on the same corpus with
#: ``python scripts/chord_benchmark.py --fit-confidence``. Earlier fits (the
#: ``tuning="auto"`` binary-template fit, slope 24.2814 / intercept 0.1552, the
#: ``tuning="zero"`` binary-template fit, slope 23.4861 / intercept 0.1973, and
#: the sqrt/harmonic fit before the minimum-duration change, slope 29.8735 /
#: intercept -0.1484) are recorded in the measurement log for history only.
CONFIDENCE_SLOPE = 28.7942
CONFIDENCE_INTERCEPT = -0.0738

#: The 24 phase-1 labels: 12 major roots first, then the 12 minor ones.
TEMPLATE_LABELS: tuple[str, ...] = tuple(PITCH_CLASS_NAMES) + tuple(
    f"{root}m" for root in PITCH_CLASS_NAMES
)


def _triad_template(semitones: frozenset[int]) -> tuple[float, ...]:
    """A 12-bin template that is 1.0 on the triad's pitch classes, 0.0 elsewhere."""
    return tuple(1.0 if index in semitones else 0.0 for index in range(12))


def _rotate(template: tuple[float, ...], semitones: int) -> tuple[float, ...]:
    """Rotate a template so its root moves up ``semitones``."""
    return tuple(template[(index - semitones) % 12] for index in range(12))


_MAJOR = _triad_template(frozenset({0, 4, 7}))
_MINOR = _triad_template(frozenset({0, 3, 7}))

#: The 24 phase-1 templates, aligned with :data:`TEMPLATE_LABELS`.
TEMPLATES: tuple[tuple[float, ...], ...] = tuple(
    _rotate(_MAJOR, root) for root in range(12)
) + tuple(_rotate(_MINOR, root) for root in range(12))


def _harmonic_template(
    *,
    minor: bool,
    root: int,
) -> tuple[float, ...]:
    """A weighted triad with the clashing third of the opposite quality negated.

    The weights follow the physical strength of the chord tones in a plucked
    guitar: root 1.00, third 0.95, fifth 0.85. The opposite third is a
    *negative* weight (-0.35), so a frame carrying both thirds (a suspension, a
    passing tone, a badly tuned recording) cannot look like a clean triad. This
    is an original weighting; the measurement that supports it is in
    ``docs/ENGINE_COMPARISON.md`` §8.
    """
    third = 3 if minor else 4
    avoid = 4 if minor else 3
    vector = [0.0] * 12
    vector[(root + 0) % 12] = 1.00
    vector[(root + third) % 12] = 0.95
    vector[(root + 7) % 12] = 0.85
    vector[(root + avoid) % 12] = -0.35
    return tuple(vector)


#: The 24 harmonic templates, aligned with :data:`TEMPLATE_LABELS`.
HARMONIC_TEMPLATES: tuple[tuple[float, ...], ...] = tuple(
    _harmonic_template(minor=False, root=root) for root in range(12)
) + tuple(_harmonic_template(minor=True, root=root) for root in range(12))

#: Selectable template sets, by option value.
_TEMPLATE_SETS: dict[str, tuple[tuple[float, ...], ...]] = {
    "binary": TEMPLATES,
    "harmonic": HARMONIC_TEMPLATES,
}

#: Norm of every template in each set, so a frame score does not recompute it.
_TEMPLATE_NORMS: dict[str, tuple[float, ...]] = {
    name: tuple(math.sqrt(sum(value * value for value in template)) for template in templates)
    for name, templates in _TEMPLATE_SETS.items()
}


def _chord_scores(
    frame: Sequence[float],
    *,
    weighting: str = "binary",
) -> list[float]:
    """Cosine similarity of one chroma frame to each of the 24 triad templates.

    ``weighting`` selects the template set: ``"binary"`` is the original
    three-bins-at-1.0 geometry, ``"harmonic"`` weights the chord tones and
    penalises the clashing third. An unknown value is a programming error, not
    user input, and raises ``ValueError`` immediately.
    """
    templates = _TEMPLATE_SETS.get(weighting)
    if templates is None:
        raise ValueError(f"unknown template weighting: {weighting!r}")
    norms = _TEMPLATE_NORMS[weighting]
    norm = math.sqrt(sum(float(value) * float(value) for value in frame))
    if norm <= 0.0:
        return [0.0] * len(TEMPLATE_LABELS)
    scores: list[float] = []
    for template, template_norm in zip(templates, norms, strict=True):
        dot = sum(
            float(value) * weight for value, weight in zip(frame, template, strict=True) if weight
        )
        scores.append(dot / (norm * template_norm))
    return scores


def frame_scores(
    frames: Sequence[Sequence[float]],
    *,
    no_chord_score: float = DEFAULT_NO_CHORD_SCORE,
    weighting: str = "binary",
) -> list[list[float]]:
    """Per-frame scores over the 24 triad states plus a no-chord state.

    The last column is the constant ``no_chord_score``, so the sequence decoder
    treats *no chord* as one more state with a fixed, modest affinity rather
    than a post-hoc threshold: ``N`` is only chosen when no triad clearly wins
    and paying the change penalty to enter it is still worth it.

    ``weighting`` defaults to ``"binary"`` so the function's historical contract
    is unchanged; the engine passes its measured ``"harmonic"`` default.
    """
    return [[*_chord_scores(frame, weighting=weighting), no_chord_score] for frame in frames]


def match_frames(
    frames: Sequence[Sequence[float]],
    *,
    threshold: float = DEFAULT_MATCH_THRESHOLD,
    weighting: str = "binary",
) -> list[str]:
    """The best triad label for every chroma frame, or ``N`` when nothing fits.

    Each frame is compared against all 24 templates by cosine similarity. A
    frame whose best score is below ``threshold`` — or a silent frame with no
    energy at all — is reported as no-chord instead of being forced onto the
    closest chord, so uncertainty survives (roadmap section 43).

    Args:
        frames: Chroma frames, each a 12-value pitch-class vector.
        threshold: Minimum cosine similarity to report a chord.

    Returns:
        One label per frame, in the same order.
    """
    labels: list[str] = []
    for frame in frames:
        scores = _chord_scores(frame, weighting=weighting)
        best_index = max(range(len(scores)), key=scores.__getitem__)
        labels.append(TEMPLATE_LABELS[best_index] if scores[best_index] >= threshold else "N")
    return labels


def decode_labels(
    frames: Sequence[Sequence[float]],
    *,
    decoder: str = DEFAULT_DECODER,
    threshold: float = DEFAULT_MATCH_THRESHOLD,
    smoothing_window: int = DEFAULT_SMOOTHING_WINDOW,
    change_penalty: float = DEFAULT_CHANGE_PENALTY,
    no_chord_score: float = DEFAULT_NO_CHORD_SCORE,
    weighting: str = "binary",
    scores: Sequence[Sequence[float]] | None = None,
) -> list[str]:
    """Decode one label per frame with the selected temporal model.

    ``"majority"`` is the section-19 baseline (per-frame argmax against the
    templates, then a majority filter). ``"viterbi"`` (section 20) runs a
    max-sum Viterbi over the 25 states (24 triads plus no-chord) with a flat
    change penalty, so isolated flips are suppressed by the model itself
    instead of by a fixed-width window.

    ``scores`` lets a caller that already ran :func:`frame_scores` for the same
    parameters reuse the result instead of scoring every frame twice; it must
    hold one row per frame in frame order. It is ignored by the ``"majority"``
    decoder, which works from the labels alone.

    Raises:
        ValueError: When ``decoder`` is unknown or the decoder parameters are
            invalid (a negative ``change_penalty``).
    """
    if decoder == "majority":
        return smooth_labels(
            match_frames(frames, threshold=threshold, weighting=weighting), width=smoothing_window
        )
    if decoder == "viterbi":
        emissions = (
            frame_scores(frames, no_chord_score=no_chord_score, weighting=weighting)
            if scores is None
            else scores
        )
        path = viterbi_decode(emissions, change_penalty=change_penalty)
        return [TEMPLATE_LABELS[index] if index < len(TEMPLATE_LABELS) else "N" for index in path]
    raise ValueError(f"unknown decoder: {decoder!r} (expected 'majority' or 'viterbi')")


def smooth_labels(
    labels: Sequence[str],
    *,
    width: int = DEFAULT_SMOOTHING_WINDOW,
) -> list[str]:
    """Remove isolated frame flips with a majority filter.

    The centre label wins ties, so boundaries between two long runs stay
    where the decoder put them while one-frame blips inside a run disappear.
    ``width`` of 1 (or less) returns the sequence unchanged.
    """
    if width <= 1 or not labels:
        return list(labels)
    half = width // 2
    smoothed: list[str] = []
    for index, centre in enumerate(labels):
        window = labels[max(0, index - half) : index + half + 1]
        counts = Counter(window)
        best = max(counts.values())
        if counts.get(centre, 0) == best:
            smoothed.append(centre)
        else:
            smoothed.append(next(label for label, count in counts.items() if count == best))
    return smoothed


def segments_from_labels(
    labels: Sequence[str],
    *,
    frame_period: float,
    duration: float | None = None,
    offset: float = 0.0,
) -> list[tuple[float, float, str]]:
    """Collapse runs of equal labels into timed ``(start, end, label)`` segments.

    Boundaries come from the frame grid alone. The final end is clamped to
    ``duration`` — an absolute time — when the caller knows where the analysed
    window really ends, because the last analysis frame extends past the
    audio's end; the start of every segment is shifted by ``offset`` when only
    a time range was decoded.
    """
    if not labels:
        return []
    if frame_period <= 0.0:
        raise ValueError("frame_period must be positive")
    segments: list[tuple[float, float, str]] = []
    run_start = 0
    for index in range(1, len(labels) + 1):
        if index == len(labels) or labels[index] != labels[run_start]:
            start = offset + run_start * frame_period
            end = offset + index * frame_period
            segments.append((start, end, labels[run_start]))
            run_start = index
    if duration is not None and duration > 0.0:
        last_start, last_end, last_label = segments[-1]
        if last_start < duration < last_end:
            segments[-1] = (last_start, duration, last_label)
    return segments


def merge_short_segments(
    segments: Sequence[tuple[float, float, str]],
    *,
    minimum_duration: float,
) -> list[tuple[float, float, str]]:
    """Merge segments shorter than ``minimum_duration`` into a neighbour.

    A short segment joins the previous one when there is one (the timeline
    stays a partition; only the boundary moves and the previous label wins).
    A short segment at the very beginning is held until the next segment
    arrives and is absorbed into it instead, so no label is ever duplicated
    across a boundary. ``minimum_duration`` of 0 returns the input unchanged,
    and adjacent segments left with the same label are coalesced. Segment
    times are never altered beyond moving a boundary — no new label is
    invented.
    """
    if minimum_duration <= 0.0 or not segments:
        return list(segments)

    merged: list[tuple[float, float, str]] = []
    pending_start: float | None = None
    last_end = 0.0
    last_label = segments[0][2]
    for start, end, label in segments:
        last_end, last_label = end, label
        if pending_start is not None:
            start = pending_start
            pending_start = None
        if (end - start) < minimum_duration:
            if merged:
                merged[-1] = (merged[-1][0], end, merged[-1][2])
            else:
                pending_start = start
        else:
            merged.append((start, end, label))
    if pending_start is not None:
        merged.append((pending_start, last_end, last_label))

    coalesced: list[tuple[float, float, str]] = []
    for segment in merged:
        if coalesced and coalesced[-1][2] == segment[2]:
            coalesced[-1] = (coalesced[-1][0], segment[1], segment[2])
        else:
            coalesced.append(segment)
    return coalesced


def events_from_segments(
    segments: Sequence[tuple[float, float, str]],
    *,
    source: str = ENGINE_NAME,
    margins: Sequence[float] | None = None,
) -> list[ChordEvent]:
    """Turn timed label segments into canonical :class:`ChordEvent` objects.

    Only the phase-1 vocabulary appears here: a root renders as a major chord,
    ``rootm`` as minor and ``N`` as an explicit no-chord event. Every event
    carries ``source`` so provenance survives into the benchmark report.

    ``margins`` — one value per segment, as :func:`segment_margins` measures it
    — becomes the event's confidence through :func:`margin_confidence`, and the
    raw margin is kept in ``event.metadata["score_margin"]`` so the derived
    number can be audited against its evidence. Without it every event reports
    ``unknown`` confidence, which is not the same as zero.

    Raises:
        ValueError: When ``margins`` and ``segments`` have different lengths.
    """
    if margins is not None and len(margins) != len(segments):
        raise ValueError(
            f"got {len(margins)} margins for {len(segments)} segments; "
            "every segment needs exactly one margin"
        )
    events: list[ChordEvent] = []
    for index, (start, end, label) in enumerate(segments):
        confidence = ConfidenceScore.unknown(source)
        metadata: dict[str, Any] = {}
        if margins is not None:
            margin = float(margins[index])
            confidence = ConfidenceScore.from_value(margin_confidence(margin), source=source)
            metadata["score_margin"] = round(margin, 6)
        if label == "N":
            events.append(
                ChordEvent.silence(
                    start,
                    end,
                    source=source,
                    confidence=confidence,
                    metadata=metadata,
                )
            )
            continue
        minor = label.endswith("m")
        root = label[:-1] if minor else label
        quality = ChordQuality.MINOR if minor else ChordQuality.MAJOR
        events.append(
            ChordEvent(
                start=start,
                end=end,
                root=root,
                quality=quality,
                confidence=confidence,
                source=source,
                metadata=metadata,
            )
        )
    return events


def _state_index(label: str) -> int:
    """The column of ``label`` in a :func:`frame_scores` row (``N`` is last)."""
    if label == "N":
        return len(TEMPLATE_LABELS)
    try:
        return TEMPLATE_LABELS.index(label)
    except ValueError:
        raise ValueError(f"unknown chord label: {label!r}") from None


def _frame_index(time: float, offset: float, frame_period: float, count: int) -> int:
    """The frame index a segment boundary falls on, clamped to ``[0, count]``."""
    index = round((time - offset) / frame_period)
    return min(max(index, 0), count)


def segment_margins(
    scores: Sequence[Sequence[float]],
    segments: Sequence[tuple[float, float, str]],
    *,
    frame_period: float,
    offset: float = 0.0,
    frame_count: int | None = None,
) -> list[float]:
    """The mean score margin of each segment's own label, over its frames.

    For every frame of a segment the *margin* is the score of the segment's
    label minus the best score any other state reaches on that frame — the
    ``N`` state included. Averaging over the segment answers the question a
    confidence is supposed to answer: over the time this chord claims, how much
    better did the decoder's answer score than the nearest alternative?

    A frame the decoder kept on its label against the frame's own preference
    contributes a negative margin, so smoothed boundaries are visible in the
    number instead of being hidden by it. The average is not clamped: the
    scale is the score's own, and :func:`margin_confidence` maps it to
    ``[0, 1]``.

    ``segments`` must partition the frames in order, as
    :func:`segments_from_labels` and :func:`merge_short_segments` leave them:
    each segment runs from its own start to the next segment's start, and the
    last one to the end of the frame grid, so a ``duration``-clamped end cannot
    make the last frames disappear. ``scores`` are the rows of
    :func:`frame_scores` (or of :func:`frame_scores` with a custom
    ``no_chord_score``) that produced those labels.

    Args:
        scores: One score row per frame, in frame order.
        segments: Timed ``(start, end, label)`` segments partitioning the frames.
        frame_period: Seconds per frame (``hop_length / sample_rate``).
        offset: Time of the first frame in the analysed timeline (seconds).
        frame_count: Number of frames that belong to the segments; defaults to
            ``len(scores)``.

    Returns:
        One mean margin per segment, in the given order. A segment that owns no
        frame reports ``0.0`` (no evidence either way), which maps to the
        middle of the confidence scale rather than to a confident answer.

    Raises:
        ValueError: When ``frame_period`` is not positive, ``frame_count`` is
            outside ``[0, len(scores)]``, or a segment carries a label the
            phase-1 vocabulary does not know.
    """
    if frame_period <= 0.0:
        raise ValueError("frame_period must be positive")
    count = len(scores) if frame_count is None else frame_count
    if count < 0 or count > len(scores):
        raise ValueError(f"frame_count {count} is outside the {len(scores)} available frames")

    margins: list[float] = []
    for position, (start, _end, label) in enumerate(segments):
        state = _state_index(label)
        first = _frame_index(start, offset, frame_period, count)
        if position + 1 < len(segments):
            stop = _frame_index(segments[position + 1][0], offset, frame_period, count)
        else:
            stop = count
        stop = max(first, stop)
        if stop == first:
            margins.append(0.0)
            continue
        total = 0.0
        for frame in scores[first:stop]:
            best_other = max(value for index, value in enumerate(frame) if index != state)
            total += float(frame[state]) - float(best_other)
        margins.append(total / (stop - first))
    return margins


def margin_confidence(margin: float) -> float:
    """Map a mean score margin to a confidence in ``(0, 1)``.

    A logistic with the constants fitted on GuitarSet (see
    :data:`CONFIDENCE_SLOPE`), evaluated so neither tail overflows: a margin of
    ``0.0`` — the decoder's label no better than the best alternative — lands
    near the middle of the scale, and larger margins approach 1.0
    monotonically. The result is a probability *on that corpus*; see the
    constants for the caveat.
    """
    z = CONFIDENCE_SLOPE * float(margin) + CONFIDENCE_INTERCEPT
    if z >= 0.0:
        return 1.0 / (1.0 + math.exp(-z))
    scaled = math.exp(z)
    return scaled / (1.0 + scaled)


@dataclass(frozen=True)
class FrontEndSettings:
    """The front end an ``analyze()`` call will use, validated before any DSP.

    Every field corresponds to one ``options.extra`` key, so a benchmark can
    change one variable at a time (audit P3) and record what actually ran.
    """

    feature: str = DEFAULT_FEATURE
    tuning: str = DEFAULT_TUNING
    harmonic: bool = DEFAULT_HARMONIC
    energy_gate_db: float = DEFAULT_ENERGY_GATE_DB

    def as_dict(self) -> dict[str, Any]:
        """The settings as JSON-safe metadata."""
        return {
            "feature": self.feature,
            "tuning": self.tuning,
            "harmonic": self.harmonic,
            "energy_gate_db": self.energy_gate_db,
        }


def front_end_settings(extra: Mapping[str, Any]) -> FrontEndSettings:
    """Read and validate the front-end options from ``ChordAnalysisOptions.extra``.

    Validation happens before the audio is decoded, so a typo costs nothing and
    the error names the accepted values instead of surfacing as a librosa
    ``TypeError`` later.

    Raises:
        InputError: When a feature, tuning mode or gate value is not supported.
    """
    feature = str(extra.get("feature", DEFAULT_FEATURE))
    if feature not in SUPPORTED_FEATURES:
        raise InputError(
            f"Unknown chroma feature: {feature!r}",
            hint=f"Supported features: {', '.join(SUPPORTED_FEATURES)}.",
        )
    tuning = str(extra.get("tuning", DEFAULT_TUNING))
    if tuning not in SUPPORTED_TUNING:
        raise InputError(
            f"Unknown tuning mode: {tuning!r}",
            hint=f"Supported modes: {', '.join(SUPPORTED_TUNING)}.",
        )
    try:
        energy_gate_db = float(extra.get("energy_gate_db", DEFAULT_ENERGY_GATE_DB))
    except (TypeError, ValueError) as error:
        raise InputError(
            f"energy_gate_db must be a number, got {extra.get('energy_gate_db')!r}",
            hint="Use 0 to disable the gate, or a negative dB threshold such as -40.",
        ) from error
    if energy_gate_db > 0.0:
        raise InputError(
            f"energy_gate_db must not be positive, got {energy_gate_db!r}",
            hint="The gate is measured downwards from the loudest frame: 0 disables it or use -40.",
        )
    return FrontEndSettings(
        feature=feature,
        tuning=tuning,
        harmonic=bool(extra.get("harmonic", DEFAULT_HARMONIC)),
        energy_gate_db=energy_gate_db,
    )


def feature_transform(extra: Mapping[str, Any]) -> str:
    """The validated per-frame chroma compression from ``options.extra``.

    Raises:
        InputError: When the requested transform is not supported. Validation
            happens before decoding, so a typo costs no DSP time and the message
            names the accepted values.
    """
    value = str(extra.get("feature_transform", DEFAULT_FEATURE_TRANSFORM))
    if value not in SUPPORTED_FEATURE_TRANSFORMS:
        raise InputError(
            f"Unknown chroma transform: {value!r}",
            hint=f"Supported transforms: {', '.join(SUPPORTED_FEATURE_TRANSFORMS)}.",
        )
    return value


def template_weighting(extra: Mapping[str, Any]) -> str:
    """The validated template set from ``options.extra``.

    Raises:
        InputError: When the requested weighting is not supported.
    """
    value = str(extra.get("template_weighting", DEFAULT_TEMPLATE_WEIGHTING))
    if value not in SUPPORTED_TEMPLATE_WEIGHTINGS:
        raise InputError(
            f"Unknown template weighting: {value!r}",
            hint=f"Supported weightings: {', '.join(SUPPORTED_TEMPLATE_WEIGHTINGS)}.",
        )
    return value


def apply_feature_transform(
    frames: Sequence[Sequence[float]],
    transform: str,
) -> list[list[float]]:
    """Compress every chroma frame before template matching.

    ``"raw"`` returns a copy of the frames, ``"sqrt"`` takes the square root of
    each bin and ``"log"`` applies ``log1p(15 * bin)``. Both compressions keep a
    frame's shape and preserve zero bins, so a silent frame stays silent and can
    still only be decoded as ``N``.

    Raises:
        InputError: When ``transform`` is not one of the supported values.
    """
    if transform == "raw":
        return [list(frame) for frame in frames]
    if transform == "sqrt":
        return [[math.sqrt(max(0.0, float(value))) for value in frame] for frame in frames]
    if transform == "log":
        return [[math.log1p(15.0 * max(0.0, float(value))) for value in frame] for frame in frames]
    raise InputError(
        f"Unknown chroma transform: {transform!r}",
        hint=f"Supported transforms: {', '.join(SUPPORTED_FEATURE_TRANSFORMS)}.",
    )


def compute_chroma(
    librosa: Any,
    numpy: Any,
    samples: Any,
    sample_rate: float,
    settings: FrontEndSettings,
    *,
    hop_length: int = HOP_LENGTH,
) -> tuple[list[list[float]], dict[str, Any]]:
    """Turn decoded samples into chroma frames for ``settings``.

    The defaults are the front end the *current* recorded measurement uses, so
    a default run is a pure refactor: CQT chroma at ``hop_length`` on the
    decoded mix, assuming A440 equal temperament. Each option changes exactly
    one thing (audit P3):

    * ``harmonic`` analyses the harmonic component of an HPSS split;
    * ``tuning`` selects how the CQT treats tuning: ``"auto"`` lets librosa
      estimate it (the historical default), ``"zero"`` assumes A440 and
      ``"estimate"`` measures it here, records it and passes it explicitly;
    * ``feature="cens"`` swaps the CQT chroma for chroma CENS, which smooths
      over time;
    * ``energy_gate_db`` zeros frames whose RMS is that far below the loudest
      frame, so near-silence can only be decoded as ``N``.

    Args:
        librosa: The imported librosa module (injected so the caller imports it
            once and tests can pass a stand-in).
        numpy: The imported numpy module, used for the RMS gate.
        samples: Mono samples in ``[-1, 1]``.
        sample_rate: Sample rate of ``samples`` in Hz.
        settings: The validated front-end options.
        hop_length: Frame hop in samples.

    Returns:
        ``(frames, metadata)``: one 12-value chroma frame per row, and the
        measured facts about the run (feature, tuning in cents, gate count).
    """
    signal = samples
    if settings.harmonic:
        harmonic, _percussive = librosa.effects.hpss(y=samples)
        signal = harmonic

    # ``auto`` must not pass the keyword at all: ``tuning=None`` asks librosa to
    # estimate it, which is what the engine did before the default moved to
    # ``zero`` (docs/ENGINE_COMPARISON.md §7).
    tuning_cents = 0.0
    tuning_bins: float | None = 0.0
    if settings.tuning == "auto":
        tuning_bins = None
    elif settings.tuning == "estimate":
        semitones = float(librosa.estimate_tuning(y=signal, sr=int(sample_rate)))
        tuning_cents = round(semitones * 100.0, 2)
        tuning_bins = semitones * CQT_BINS_PER_OCTAVE / 12.0

    if settings.feature == "cens":
        chroma = librosa.feature.chroma_cens(
            y=signal,
            sr=int(sample_rate),
            hop_length=hop_length,
        )
    else:
        cqt_options: dict[str, Any] = {
            "y": signal,
            "sr": int(sample_rate),
            "hop_length": hop_length,
        }
        if tuning_bins is not None:
            cqt_options["tuning"] = tuning_bins
        chroma = librosa.feature.chroma_cqt(**cqt_options)
    frames = chroma.T.tolist()

    gated = 0
    if settings.energy_gate_db < 0.0 and frames:
        rms = numpy.asarray(librosa.feature.rms(y=signal, hop_length=hop_length)[0])
        peak = float(rms.max()) if rms.size else 0.0
        if peak > 0.0:
            floor = peak * 10.0 ** (settings.energy_gate_db / 20.0)
            allowed = [bool(value >= floor) for value in rms[: len(frames)]]
            allowed.extend([True] * (len(frames) - len(allowed)))
            for index, keep in enumerate(allowed):
                if not keep:
                    frames[index] = [0.0] * 12
                    gated += 1

    metadata = settings.as_dict()
    metadata["tuning_cents"] = tuning_cents
    metadata["energy_gate_frames"] = gated
    return frames, metadata


def _import_front_end() -> tuple[Any, Any]:
    """Import the optional DSP stack, or raise ``ImportError``.

    Uses :func:`importlib.import_module` so the core package stays importable
    and type-checkable without numpy or librosa installed.
    """
    librosa = importlib.import_module("librosa")
    numpy = importlib.import_module("numpy")
    return librosa, numpy


class ChromaBaselineEngine:
    """Chroma template baseline: CQT chroma matched against triad templates.

    Implements the roadmap section 13 phase-1 vocabulary only (major, minor
    and no-chord); requesting a later vocabulary phase is refused instead of
    silently returning fewer chord qualities than asked for.
    """

    name = ENGINE_NAME
    kind = EngineKind.CHORDS

    def is_available(self) -> bool:
        """Whether numpy and librosa can be imported right now."""
        try:
            _import_front_end()
        except ImportError:
            return False
        return True

    def engine_info(self) -> EngineInfo:
        """Identity and capability metadata recorded as provenance."""
        return EngineInfo(
            name=self.name,
            kind=self.kind.value,
            version=ENGINE_VERSION,
            available=self.is_available(),
            description=(
                "CQT chroma compressed per frame and matched against 24 "
                "harmonic-weighted triad templates by cosine similarity, with "
                "a majority smoother or a Viterbi decoder, a minimum-duration "
                "merge, and a per-event confidence from the score margin."
            ),
            license="GPL-3.0-or-later",
            capabilities={
                "vocabulary_phase": 1,
                "device": "cpu",
                "no_chord": True,
                "confidence": True,
                "confidence_method": "score_margin_logistic",
                "feature_transform": DEFAULT_FEATURE_TRANSFORM,
                "template_weighting": DEFAULT_TEMPLATE_WEIGHTING,
                "minimum_segment_seconds": DEFAULT_MIN_SEGMENT_SECONDS,
            },
        )

    def analyze(
        self,
        audio_path: Path,
        options: ChordAnalysisOptions,
    ) -> EngineResult:
        """Estimate phase-1 chords for ``audio_path``.

        Raises:
            AudioFileNotFoundError: When the audio file does not exist.
            InputError: When a vocabulary phase beyond 1 is requested.
            DependencyError: When numpy/librosa are not installed.
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise AudioFileNotFoundError(audio_path)
        if options.vocabulary_phase > 1:
            raise InputError(
                f"{self.name} implements the phase 1 vocabulary (major, minor, N)",
                hint="Pass vocabulary_phase=1 or choose a richer engine.",
            )

        # Validate the front-end options before decoding: a typo costs nothing.
        settings = front_end_settings(options.extra)
        transform = feature_transform(options.extra)
        weighting = template_weighting(options.extra)

        startup_started = time.perf_counter()
        try:
            librosa, numpy = _import_front_end()
        except ImportError as error:
            raise DependencyError(
                f"Engine {self.name!r} needs numpy and librosa, which are not installed.",
                hint="Install the optional DSP stack: pip install numpy librosa",
            ) from error
        startup_seconds = time.perf_counter() - startup_started

        probe = PerformanceProbe(startup_time_seconds=startup_seconds, device="cpu")
        probe.start()
        try:
            offset = float(options.start) if options.start is not None else 0.0
            window = float(options.end) - offset if options.end is not None else None
            decoded = decode_audio(
                audio_path,
                sample_rate=SAMPLE_RATE,
                mono=True,
                offset=offset,
                duration=window,
            )
            samples = numpy.asarray(decoded.samples)
            sample_rate = decoded.sample_rate
            audio_seconds = decoded.duration
            probe.audio_seconds = audio_seconds

            frames, front_end_metadata = compute_chroma(
                librosa, numpy, samples, float(sample_rate), settings
            )
            frames = apply_feature_transform(frames, transform)
            frame_period = HOP_LENGTH / float(sample_rate)

            decoder = str(options.extra.get("decoder", DEFAULT_DECODER))
            change_penalty = float(options.extra.get("change_penalty", DEFAULT_CHANGE_PENALTY))
            no_chord_score = float(options.extra.get("no_chord_score", DEFAULT_NO_CHORD_SCORE))
            raw_labels = match_frames(frames, weighting=weighting)
            scores = frame_scores(frames, no_chord_score=no_chord_score, weighting=weighting)
            try:
                labels = decode_labels(
                    frames,
                    decoder=decoder,
                    change_penalty=change_penalty,
                    no_chord_score=no_chord_score,
                    weighting=weighting,
                    scores=scores,
                )
            except ValueError as error:
                raise InputError(
                    str(error),
                    hint="Supported decoders: 'majority', 'viterbi'.",
                ) from error
            segments = segments_from_labels(
                labels,
                frame_period=frame_period,
                duration=offset + audio_seconds,
                offset=offset,
            )
            try:
                minimum_duration = float(
                    options.extra.get("min_segment_seconds", options.minimum_duration)
                )
            except (TypeError, ValueError) as error:
                raise InputError(
                    "minimum chord duration must be a number, "
                    f"got {options.extra.get('min_segment_seconds')!r}",
                    hint="Use 0 to disable the merge, or a positive number of seconds.",
                ) from error
            if minimum_duration < 0.0:
                raise InputError(
                    f"minimum chord duration must not be negative, got {minimum_duration!r}",
                    hint="Use 0 to disable the merge, or a positive number of seconds.",
                )
            if minimum_duration > 0.0:
                segments = merge_short_segments(segments, minimum_duration=minimum_duration)
            # Confidence is measured *after* merging, against the label each
            # surviving segment actually claims: a merged-in chord is not
            # credited with the margin of the label it replaced.
            margins = segment_margins(
                scores,
                segments,
                frame_period=frame_period,
                offset=offset,
                frame_count=len(labels),
            )
            events = events_from_segments(segments, source=self.name, margins=margins)
        finally:
            report = probe.stop()

        return EngineResult(
            engine=self.name,
            kind=self.kind.value,
            engine_version=ENGINE_VERSION,
            audio_path=audio_path,
            chords=events,
            processing_time_seconds=report.processing_time_seconds,
            raw={"frame_labels": raw_labels},
            metadata={
                "performance": report.as_dict(),
                "frame_period_seconds": frame_period,
                "sample_rate": SAMPLE_RATE,
                "hop_length": HOP_LENGTH,
                "match_threshold": DEFAULT_MATCH_THRESHOLD,
                # The Viterbi decoder never consults the match threshold or
                # the smoother; the flags say so instead of letting the values
                # look like they shaped this run.
                "match_threshold_used": decoder == "majority",
                "smoothing_window_used": decoder == "majority",
                **front_end_metadata,
                "feature_transform": transform,
                "template_weighting": weighting,
                "minimum_duration": minimum_duration,
                "decoder": decoder,
                "change_penalty": change_penalty,
                "no_chord_score": no_chord_score,
                "smoothing_window": DEFAULT_SMOOTHING_WINDOW,
                "confidence_method": "score_margin_logistic",
                "confidence_slope": CONFIDENCE_SLOPE,
                "confidence_intercept": CONFIDENCE_INTERCEPT,
            },
        )
