"""Chroma template baseline chord engine (roadmap sections 13, 14, 18, 19 and 59).

The first concrete engine behind the
:class:`~song_chord_lyrics_analyzer.engines.base.ChordEngine` protocol. It is
deliberately simple and fully inspectable:

1. decode the audio to mono 22.05 kHz (librosa);
2. compute per-frame CQT chroma;
3. match every frame against the 24 phase-1 triad templates (12 major, 12
   minor) by cosine similarity, reporting ``N`` when no template fits;
4. decode the frame scores into a label sequence — either a majority filter
   (roadmap section 19) or a max-sum Viterbi over a flat change penalty
   (roadmap section 20; the default, selectable through ``options.extra``);
5. collapse runs of equal labels into timed :class:`ChordEvent` segments.

The DSP front end (numpy + librosa) is **optional**: :meth:`ChromaBaselineEngine.is_available`
reports whether it is importable, and :meth:`ChromaBaselineEngine.analyze` raises
:class:`~song_chord_lyrics_analyzer.utils.errors.DependencyError` with an
install hint instead of failing obscurely. Steps 3-5 are dependency-free
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
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from song_chord_lyrics_analyzer.engines.base import ChordAnalysisOptions, EngineKind
from song_chord_lyrics_analyzer.engines.decoding import viterbi_decode
from song_chord_lyrics_analyzer.models.analysis import EngineInfo, EngineResult
from song_chord_lyrics_analyzer.models.music import PITCH_CLASS_NAMES, ChordEvent, ChordQuality
from song_chord_lyrics_analyzer.performance import PerformanceProbe
from song_chord_lyrics_analyzer.utils.errors import (
    AudioFileNotFoundError,
    DependencyError,
    InputError,
)

__all__ = [
    "DEFAULT_CHANGE_PENALTY",
    "DEFAULT_DECODER",
    "DEFAULT_MATCH_THRESHOLD",
    "DEFAULT_NO_CHORD_SCORE",
    "DEFAULT_SMOOTHING_WINDOW",
    "ENGINE_NAME",
    "ENGINE_VERSION",
    "HOP_LENGTH",
    "SAMPLE_RATE",
    "TEMPLATE_LABELS",
    "ChromaBaselineEngine",
    "decode_labels",
    "events_from_segments",
    "frame_scores",
    "match_frames",
    "merge_short_segments",
    "segments_from_labels",
    "smooth_labels",
]

#: Stable, CLI-facing engine identifier.
ENGINE_NAME = "chroma-baseline"
#: Engine version recorded as provenance in every result.
ENGINE_VERSION = "0.1.0"

#: Audio decoded to this mono sample rate before analysis.
SAMPLE_RATE = 22_050
#: Chroma frame hop in samples (~93 ms, ~10.7 frames per second).
HOP_LENGTH = 2_048

#: Cosine similarity a frame needs to be reported as a chord instead of ``N``.
#: Frames below it are honest no-chord readings, not forced matches.
DEFAULT_MATCH_THRESHOLD = 0.5
#: Majority-filter window (in frames) that removes isolated label flips.
DEFAULT_SMOOTHING_WINDOW = 5

#: Temporal decoder: ``"majority"`` (per-frame argmax + majority smoother,
#: roadmap section 19) or ``"viterbi"`` (max-sum sequence decoding, roadmap
#: section 20).
DEFAULT_DECODER = "viterbi"
#: Flat transition cost per chord change for the Viterbi decoder. ``0.0``
#: decodes every frame independently. ``0.80`` is the measured optimum on 180
#: real GuitarSet takes (CSR, segment overlap and change-detection F1); CSR
#: alone would push it higher at the cost of change-detection F1. The measured
#: comparison lives in ``docs/ENGINE_COMPARISON.md``.
DEFAULT_CHANGE_PENALTY = 0.80
#: Emission score of the Viterbi no-chord state. It is a constant, so a frame
#: is decoded as ``N`` only when no triad outscores it by enough *and* the
#: change costs the transition penalty.
DEFAULT_NO_CHORD_SCORE = 0.06

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

#: Norm shared by every triad template (three 1.0 bins): sqrt(3).
_TEMPLATE_NORM = math.sqrt(3.0)


def _chord_scores(frame: Sequence[float]) -> list[float]:
    """Cosine similarity of one chroma frame to each of the 24 triad templates."""
    norm = math.sqrt(sum(float(value) * float(value) for value in frame))
    if norm <= 0.0:
        return [0.0] * len(TEMPLATE_LABELS)
    scores: list[float] = []
    for template in TEMPLATES:
        dot = sum(
            float(value) * weight for value, weight in zip(frame, template, strict=True) if weight
        )
        scores.append(dot / (norm * _TEMPLATE_NORM))
    return scores


def frame_scores(
    frames: Sequence[Sequence[float]],
    *,
    no_chord_score: float = DEFAULT_NO_CHORD_SCORE,
) -> list[list[float]]:
    """Per-frame scores over the 24 triad states plus a no-chord state.

    The last column is the constant ``no_chord_score``, so the sequence decoder
    treats *no chord* as one more state with a fixed, modest affinity rather
    than a post-hoc threshold: ``N`` is only chosen when no triad clearly wins
    and paying the change penalty to enter it is still worth it.
    """
    return [[*_chord_scores(frame), no_chord_score] for frame in frames]


def match_frames(
    frames: Sequence[Sequence[float]],
    *,
    threshold: float = DEFAULT_MATCH_THRESHOLD,
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
        scores = _chord_scores(frame)
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
) -> list[str]:
    """Decode one label per frame with the selected temporal model.

    ``"majority"`` is the section-19 baseline (per-frame argmax against the
    templates, then a majority filter). ``"viterbi"`` (section 20) runs a
    max-sum Viterbi over the 25 states (24 triads plus no-chord) with a flat
    change penalty, so isolated flips are suppressed by the model itself
    instead of by a fixed-width window.

    Raises:
        ValueError: When ``decoder`` is unknown or the decoder parameters are
            invalid (a negative ``change_penalty``).
    """
    if decoder == "majority":
        return smooth_labels(match_frames(frames, threshold=threshold), width=smoothing_window)
    if decoder == "viterbi":
        path = viterbi_decode(
            frame_scores(frames, no_chord_score=no_chord_score),
            change_penalty=change_penalty,
        )
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
) -> list[ChordEvent]:
    """Turn timed label segments into canonical :class:`ChordEvent` objects.

    Only the phase-1 vocabulary appears here: a root renders as a major chord,
    ``rootm`` as minor and ``N`` as an explicit no-chord event. Every event
    carries ``source`` so provenance survives into the benchmark report.
    """
    events: list[ChordEvent] = []
    for start, end, label in segments:
        if label == "N":
            events.append(ChordEvent.silence(start, end, source=source))
            continue
        minor = label.endswith("m")
        root = label[:-1] if minor else label
        quality = ChordQuality.MINOR if minor else ChordQuality.MAJOR
        events.append(ChordEvent(start=start, end=end, root=root, quality=quality, source=source))
    return events


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
                "CQT chroma matched per frame against the 24 phase-1 triad "
                "templates by cosine similarity, with a majority smoother."
            ),
            license="GPL-3.0-or-later",
            capabilities={
                "vocabulary_phase": 1,
                "device": "cpu",
                "no_chord": True,
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

        startup_started = time.perf_counter()
        try:
            librosa, _numpy = _import_front_end()
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
            samples, sample_rate = librosa.load(
                str(audio_path),
                sr=SAMPLE_RATE,
                mono=True,
                offset=offset,
                duration=window,
            )
            audio_seconds = float(len(samples)) / float(sample_rate)
            probe.audio_seconds = audio_seconds

            chroma = librosa.feature.chroma_cqt(
                y=_numpy.asarray(samples),
                sr=int(sample_rate),
                hop_length=HOP_LENGTH,
            )
            frames = chroma.T.tolist()
            frame_period = HOP_LENGTH / float(sample_rate)

            decoder = str(options.extra.get("decoder", DEFAULT_DECODER))
            change_penalty = float(options.extra.get("change_penalty", DEFAULT_CHANGE_PENALTY))
            no_chord_score = float(options.extra.get("no_chord_score", DEFAULT_NO_CHORD_SCORE))
            raw_labels = match_frames(frames)
            try:
                labels = decode_labels(
                    frames,
                    decoder=decoder,
                    change_penalty=change_penalty,
                    no_chord_score=no_chord_score,
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
            if options.minimum_duration > 0.0:
                segments = merge_short_segments(segments, minimum_duration=options.minimum_duration)
            events = events_from_segments(segments, source=self.name)
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
                "decoder": decoder,
                "change_penalty": change_penalty,
                "no_chord_score": no_chord_score,
                "smoothing_window": DEFAULT_SMOOTHING_WINDOW,
            },
        )
