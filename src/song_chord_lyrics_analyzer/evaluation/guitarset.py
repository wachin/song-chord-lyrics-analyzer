"""GuitarSet corpus: fixed takes, timed references and scoring (roadmap Phase I).

The chord engine's one recorded accuracy number is a duration-weighted CSR on
180 GuitarSet comping takes. That measurement used to live in a gitignored
harness, so it could not be re-run or checked from the repository. This module
is the reproducible half of the replacement: it reads a **committed manifest**
that pins which takes, which annotation and which bytes make up the corpus, and
it scores a hypothesis with the same primitives the rest of the package uses
(:func:`~song_chord_lyrics_analyzer.evaluation.chords.duration_csr`,
:func:`~song_chord_lyrics_analyzer.metrics.segmentation.segment_overlap`,
:func:`~song_chord_lyrics_analyzer.metrics.segmentation.chord_change_detection`,
:func:`~song_chord_lyrics_analyzer.metrics.segmentation.timing_error`).

GuitarSet is CC BY 4.0 (Zenodo 10.5281/zenodo.3371780), so its annotations may
be committed; its audio stays out of the repository (462 MB for the comp takes
alone) and is fetched separately. The manifest records the SHA-256 of both
files per take, so a corpus that differs from the measured one is refused
instead of silently producing a different number. Nothing here downloads
anything, and no number is invented: every metric is computed from explicit
reference annotations and an explicit hypothesis.

The harness that drives this module is ``scripts/chord_benchmark.py``; the
generated-fixture companion in ``tests/fixtures/audio.py`` exercises the same
scoring path offline.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from song_chord_lyrics_analyzer.evaluation.chords import (
    duration_csr,
    harte_to_label,
    triad_reduce,
)
from song_chord_lyrics_analyzer.metrics.segmentation import (
    chord_change_detection,
    segment_overlap,
    timing_error,
)
from song_chord_lyrics_analyzer.utils.errors import InputError

__all__ = [
    "GuitarSetManifest",
    "GuitarSetTake",
    "aggregate_scores",
    "load_manifest",
    "read_jams_chords",
    "score_take",
    "sha256_file",
    "verify_take_files",
]

#: A timed chord: ``(start, end, label)`` in seconds, label in canonical form.
ChordSegment = tuple[float, float, str]

#: GuitarSet records two chord annotations per excerpt: index 0 is the
#: instructed lead sheet, index 1 the performed voicings. They are never mixed
#: in one number, so the reference view is named explicitly everywhere.
ANNOTATION_VIEWS = ("instructed", "performed")

#: ``reference``/``performed`` map to the JAMS annotation index.
_VIEW_INDEX = {"instructed": 0, "performed": 1}

#: Hash lengths accepted for a SHA-256 hex digest.
_SHA256_LENGTH = 64


@dataclass(frozen=True)
class GuitarSetTake:
    """One GuitarSet excerpt: the two files, their hashes and its duration.

    ``audio`` and ``jams`` are file names relative to the corpus directory, so
    the manifest stays portable across machines. ``duration_seconds`` is the
    decoded audio length recorded when the manifest was generated; it lets a
    harness validate a downloaded copy without decoding it again.
    """

    name: str
    split: str
    audio: str
    jams: str
    audio_sha256: str
    jams_sha256: str
    duration_seconds: float

    def audio_path(self, corpus_dir: Path) -> Path:
        """The take's audio file inside ``corpus_dir``."""
        return Path(corpus_dir) / self.audio

    def jams_path(self, corpus_dir: Path) -> Path:
        """The take's JAMS annotation file inside ``corpus_dir``."""
        return Path(corpus_dir) / self.jams


@dataclass(frozen=True)
class GuitarSetManifest:
    """The committed corpus definition: dataset provenance plus the take list.

    ``takes`` is ordered by name so a run over "the manifest" is deterministic.
    """

    dataset: str
    version: str
    doi: str
    license: str
    retrieved: str
    notes: str
    takes: tuple[GuitarSetTake, ...]
    source: Path | None = None

    def by_name(self, name: str) -> GuitarSetTake:
        """The take called ``name``.

        Raises:
            InputError: When the manifest has no such take.
        """
        for take in self.takes:
            if take.name == name:
                return take
        raise InputError(
            f"Take {name!r} is not in the GuitarSet manifest.",
            hint=f"Available takes: {len(self.takes)} (e.g. {self.takes[0].name!r}).",
        )

    def subset(self, *, split: str | None = None) -> tuple[GuitarSetTake, ...]:
        """Every take, optionally restricted to ``comp`` or ``solo``."""
        if split is None:
            return self.takes
        selected = tuple(take for take in self.takes if take.split == split)
        if not selected:
            raise InputError(
                f"The manifest has no {split!r} takes.",
                hint="GuitarSet splits are 'comp' (comping) and 'solo' (soloing).",
            )
        return selected


def sha256_file(path: Path, *, chunk_size: int = 1 << 20) -> str:
    """SHA-256 hex digest of a file, streamed so large audio does not load."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _text(document: dict[str, Any], field: str, source: Path) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value:
        raise InputError(
            f"GuitarSet manifest {source} needs a non-empty string '{field}'.",
            hint="See docs/ENGINE_COMPARISON.md for the manifest format.",
        )
    return value


def _digest(document: dict[str, Any], field: str, source: Path) -> str:
    value = _text(document, field, source).lower()
    if len(value) != _SHA256_LENGTH or any(char not in "0123456789abcdef" for char in value):
        raise InputError(
            f"GuitarSet manifest {source}: '{field}' is not a SHA-256 hex digest.",
            hint="Record the digest produced by sha256_file() for the exact file.",
        )
    return value


def _take(document: Any, source: Path) -> GuitarSetTake:
    if not isinstance(document, dict):
        raise InputError(
            f"GuitarSet manifest {source}: every take must be an object.",
            hint="Each take needs name, split, audio, jams, hashes and duration_seconds.",
        )
    name = _text(document, "name", source)
    split = _text(document, "split", source)
    if split not in ("comp", "solo"):
        raise InputError(
            f"GuitarSet manifest {source}: take {name!r} has split {split!r}.",
            hint="GuitarSet splits are 'comp' (comping) and 'solo' (soloing).",
        )
    audio_path = _text(document, "audio", source)
    jams_path = _text(document, "jams", source)
    if Path(audio_path).is_absolute() or Path(jams_path).is_absolute():
        raise InputError(
            f"GuitarSet manifest {source}: take {name!r} uses an absolute path.",
            hint="File names are relative to the corpus directory so the manifest stays portable.",
        )
    duration = document.get("duration_seconds")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration <= 0:
        raise InputError(
            f"GuitarSet manifest {source}: take {name!r} has no positive duration_seconds.",
            hint="Record the decoded audio length in seconds.",
        )
    return GuitarSetTake(
        name=name,
        split=split,
        audio=audio_path,
        jams=jams_path,
        audio_sha256=_digest(document, "audio_sha256", source),
        jams_sha256=_digest(document, "jams_sha256", source),
        duration_seconds=float(duration),
    )


def load_manifest(path: Path) -> GuitarSetManifest:
    """Load and validate the committed GuitarSet take manifest.

    Raises:
        InputError: When the file is missing, not JSON, missing provenance, or
            carries duplicate or malformed takes.
    """
    path = Path(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise InputError(
            f"GuitarSet manifest not found: {path}",
            hint="Pass --manifest with the committed corpus definition.",
        ) from error
    except json.JSONDecodeError as error:
        raise InputError(
            f"GuitarSet manifest {path} is not valid JSON: {error}",
            hint="Fix the JSON syntax and try again.",
        ) from error
    if not isinstance(document, dict):
        raise InputError(
            f"GuitarSet manifest {path} must be a JSON object.",
            hint="See docs/ENGINE_COMPARISON.md for the manifest format.",
        )
    raw_takes = document.get("takes")
    if not isinstance(raw_takes, list) or not raw_takes:
        raise InputError(
            f"GuitarSet manifest {path} has no takes.",
            hint="Add at least one take; see docs/ENGINE_COMPARISON.md.",
        )
    takes = tuple(_take(item, path) for item in raw_takes)
    names = [take.name for take in takes]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise InputError(
            f"GuitarSet manifest {path} lists takes more than once: {', '.join(duplicates[:5])}",
            hint="A take may appear only once, so a run cannot double-count it.",
        )
    return GuitarSetManifest(
        dataset=_text(document, "dataset", path),
        version=_text(document, "version", path),
        doi=_text(document, "doi", path),
        license=_text(document, "license", path),
        retrieved=_text(document, "retrieved", path),
        notes=str(document.get("notes", "")),
        takes=tuple(sorted(takes, key=lambda take: take.name)),
        source=path,
    )


def verify_take_files(
    take: GuitarSetTake,
    corpus_dir: Path,
    *,
    check_hashes: bool = True,
) -> tuple[Path, Path]:
    """Resolve and verify one take's audio and JAMS files.

    Args:
        take: The manifest entry to look up.
        corpus_dir: Directory holding the downloaded GuitarSet files.
        check_hashes: When false, only existence is checked. The harness keeps
            this true by default: a different byte stream is a different
            measurement.

    Returns:
        ``(audio_path, jams_path)``.

    Raises:
        InputError: When a file is missing or its SHA-256 differs from the
            manifest.
    """
    audio_path = take.audio_path(corpus_dir)
    jams_path = take.jams_path(corpus_dir)
    for path, expected, kind in (
        (audio_path, take.audio_sha256, "audio"),
        (jams_path, take.jams_sha256, "JAMS"),
    ):
        if not path.exists():
            raise InputError(
                f"GuitarSet {kind} file not found for take {take.name!r}: {path}",
                hint=(
                    "Download GuitarSet v1.1.0 from Zenodo 10.5281/zenodo.3371780 "
                    "and point --corpus-dir at the extracted files."
                ),
            )
        if check_hashes:
            actual = sha256_file(path)
            if actual != expected:
                raise InputError(
                    f"GuitarSet {kind} file for take {take.name!r} does not match the manifest.",
                    hint=(
                        f"expected SHA-256 {expected}, got {actual}. "
                        "Re-download the dataset instead of measuring different bytes."
                    ),
                )
    return audio_path, jams_path


def read_jams_chords(path: Path, *, index: int = 0) -> list[ChordSegment]:
    """Read one ``chord`` annotation from a JAMS file as timed canonical labels.

    GuitarSet stores two chord annotations: index 0 is the instructed lead
    sheet, index 1 the performed voicings. Harte spellings are converted with
    :func:`~song_chord_lyrics_analyzer.evaluation.chords.harte_to_label`, so
    ``Bb:min7`` becomes ``A#m7``; observations with a non-positive duration are
    dropped exactly like the original harness did, because they occupy no time.

    Raises:
        InputError: When the file is not JSON, has no ``chord`` annotation, or
            the requested index does not exist.
    """
    path = Path(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise InputError(
            f"JAMS file {path} is not valid JSON: {error}",
            hint="Re-download the annotation archive; do not edit a JAMS by hand.",
        ) from error
    if not isinstance(document, dict) or not isinstance(document.get("annotations"), list):
        raise InputError(
            f"JAMS file {path} has no annotations list.",
            hint="This is not a JAMS document; check the file name.",
        )
    chord_annotations = [
        annotation
        for annotation in document["annotations"]
        if isinstance(annotation, dict) and annotation.get("namespace") == "chord"
    ]
    if not chord_annotations:
        raise InputError(
            f"JAMS file {path} has no chord annotation.",
            hint="GuitarSet excerpts carry both instructed and performed chord annotations.",
        )
    if index < 0 or index >= len(chord_annotations):
        raise InputError(
            f"JAMS file {path} has {len(chord_annotations)} chord annotations, not index {index}.",
            hint="Index 0 is the instructed lead sheet, index 1 the performed voicings.",
        )
    data = chord_annotations[index].get("data")
    if not isinstance(data, list):
        raise InputError(
            f"JAMS file {path}: chord annotation {index} has no data list.",
            hint="Re-download the annotation archive.",
        )
    segments: list[ChordSegment] = []
    for observation in data:
        if not isinstance(observation, dict):
            continue
        start = float(observation.get("time", 0.0))
        duration = float(observation.get("duration", 0.0))
        if duration <= 0.0:
            continue
        segments.append(
            (start, start + duration, harte_to_label(str(observation.get("value", ""))))
        )
    return segments


def _finite(value: float) -> float | None:
    """A JSON-safe float: ``None`` for NaN/inf rather than invalid JSON."""
    return value if math.isfinite(value) else None


def score_take(
    reference: list[ChordSegment],
    hypothesis: list[ChordSegment],
    *,
    change_window: float = 0.5,
    trim_changes: bool = False,
) -> dict[str, Any]:
    """Score one take with the full comparison vector (audit §11).

    The returned dict is intentionally flat and JSON-safe so one line per take
    can be appended to a JSONL file. It reports:

    * ``csr`` and ``csr_triads`` — duration-weighted CSR over the raw and the
      triad-reduced views (both sides reduced, so a vocabulary change cannot
      look better by shrinking only the hypothesis labels);
    * ``segment_overlap`` — MIREX mean segmentation;
    * ``change_precision``/``change_recall``/``change_f1`` — boundary detection
      within ``change_window`` seconds;
    * ``timing_reference_to_hypothesis``/``timing_hypothesis_to_reference`` —
      median boundary distance in both directions (``None`` when a side has no
      boundaries);
    * segment and chord counts, so a change that merely emits fewer chords is
      visible next to the accuracy numbers.

    A hypothesis label with no counterpart still occupies time and is scored as
    a miss; nothing is dropped. ``N`` matches only ``N``.
    """
    raw = duration_csr(reference, hypothesis)
    reference_triads = [(start, end, triad_reduce([label])[0]) for start, end, label in reference]
    hypothesis_triads = [(start, end, triad_reduce([label])[0]) for start, end, label in hypothesis]
    triads = duration_csr(reference_triads, hypothesis_triads)
    changes = chord_change_detection(reference, hypothesis, window=change_window, trim=trim_changes)
    timing = timing_error(reference, hypothesis)
    return {
        "reference_segments": len(reference),
        "hypothesis_segments": len(hypothesis),
        "reference_chords": sum(1 for _start, _end, label in reference if label != "N"),
        "hypothesis_chords": sum(1 for _start, _end, label in hypothesis if label != "N"),
        "csr": raw["csr"],
        "csr_triads": triads["csr"],
        "segment_overlap": segment_overlap(reference, hypothesis),
        "change_precision": changes["precision"],
        "change_recall": changes["recall"],
        "change_f1": changes["f1"],
        "timing_reference_to_hypothesis": _finite(timing["reference_to_hypothesis"]),
        "timing_hypothesis_to_reference": _finite(timing["hypothesis_to_reference"]),
    }


#: Per-take keys averaged by :func:`aggregate_scores`, in report order.
_SCORED_KEYS = (
    "csr",
    "csr_triads",
    "segment_overlap",
    "change_precision",
    "change_recall",
    "change_f1",
    "timing_reference_to_hypothesis",
    "timing_hypothesis_to_reference",
    "hypothesis_chords",
    "hypothesis_segments",
)

#: Per-take keys summed rather than averaged (counts and durations).
_SUMMED_KEYS = ("reference_chords", "reference_segments")


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def aggregate_scores(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarise per-take score rows: mean, median, min and max per metric.

    Rows missing a metric (or carrying ``None``) are skipped for that metric, so
    one take whose boundary error is undefined does not erase the aggregate.
    Returns ``{}`` for an empty input rather than inventing a zero.
    """
    if not rows:
        return {}
    summary: dict[str, Any] = {"count": len(rows)}
    for key in _SCORED_KEYS:
        values = [
            float(row[key])
            for row in rows
            if isinstance(row.get(key), (int, float)) and not isinstance(row.get(key), bool)
        ]
        if not values:
            continue
        summary[key] = {
            "mean": sum(values) / len(values),
            "median": _median(values),
            "min": min(values),
            "max": max(values),
        }
    for key in _SUMMED_KEYS:
        values = [
            int(row[key])
            for row in rows
            if isinstance(row.get(key), int) and not isinstance(row.get(key), bool)
        ]
        if values:
            summary[key] = {
                "total": sum(values),
                "mean": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
            }
    return summary
