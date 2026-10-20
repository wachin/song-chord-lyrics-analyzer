"""Chord benchmark harness tests (Phase I P1), offline and end-to-end.

``scripts/chord_benchmark.py`` is developer tooling over the GuitarSet corpus,
but its contract is the same one every later chord claim depends on: run the
registered engine, score it with the package metrics, refuse a corpus that is
not the pinned one, and refuse to invent a number when a take is missing.

These tests build a synthetic corpus in ``tmp_path`` (known triads through
``fixtures.audio.write_chord_wav`` plus a hand-written JAMS) and drive the real
script through a subprocess, so no dataset download and no network are needed.
The first test also validates the audit's check that a deliberately broken
hypothesis lowers the score.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from fixtures.audio import write_chord_wav
from song_chord_lyrics_analyzer.engines import ChromaBaselineEngine, chroma_baseline
from song_chord_lyrics_analyzer.engines.base import ChordAnalysisOptions
from song_chord_lyrics_analyzer.evaluation import score_take
from song_chord_lyrics_analyzer.metrics.adapters import chord_segments

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "chord_benchmark.py"

#: C major, G major, A minor, F major — two seconds each.
PROGRESSION: list[tuple[int, ...]] = [(0, 4, 7), (7, 11, 2), (9, 0, 4), (5, 9, 0)]
LABELS = ("C", "G", "Am", "F")
HARTE = ("C:maj", "G:maj", "A:min", "F:maj")
SECONDS_PER_CHORD = 2.0
DURATION = len(PROGRESSION) * SECONDS_PER_CHORD

ENGINE = ChromaBaselineEngine()
pytestmark = pytest.mark.skipif(
    not ENGINE.is_available(),
    reason="optional DSP stack (numpy/librosa) not installed",
)


def _reference() -> list[tuple[float, float, str]]:
    return [
        (index * SECONDS_PER_CHORD, (index + 1) * SECONDS_PER_CHORD, label)
        for index, label in enumerate(LABELS)
    ]


def _write_corpus(
    corpus_dir: Path,
    *,
    name: str = "01_Demo_comp",
    harte: tuple[str, ...] = HARTE,
) -> Path:
    """One take: ``<name>_mic.wav`` playing the progression plus its JAMS.

    ``harte`` lets a test write an annotation that disagrees with the audio,
    which is how the confidence fit gets events it knows to be wrong.
    """
    corpus_dir.mkdir(parents=True, exist_ok=True)
    write_chord_wav(
        corpus_dir / f"{name}_mic.wav",
        chords=PROGRESSION,
        seconds_per_chord=SECONDS_PER_CHORD,
    )
    jams = {
        "annotations": [
            {
                "namespace": "chord",
                "data": [
                    {"time": start, "duration": end - start, "value": value}
                    for (start, end, _label), value in zip(_reference(), harte, strict=True)
                ],
            }
        ]
    }
    path = corpus_dir / f"{name}.jams"
    path.write_text(json.dumps(jams), encoding="utf-8")
    return path


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


# --------------------------------------------------------------------------- #
# Scoring behaviour
# --------------------------------------------------------------------------- #
def test_a_broken_hypothesis_scores_below_the_engine(tmp_path: Path) -> None:
    """The audit's validation: the harness must detect a worse hypothesis."""
    audio = write_chord_wav(
        tmp_path / "progression.wav",
        chords=PROGRESSION,
        seconds_per_chord=SECONDS_PER_CHORD,
    )
    result = ENGINE.analyze(audio, ChordAnalysisOptions())
    hypothesis = chord_segments(result.chords, end=DURATION)
    reference = _reference()

    good = score_take(reference, hypothesis)
    assert good["reference_segments"] == len(PROGRESSION)
    assert good["hypothesis_segments"] == len(PROGRESSION)
    assert good["csr"] > 0.9
    assert good["segment_overlap"] > 0.9
    assert good["change_f1"] > 0.9
    assert good["timing_reference_to_hypothesis"] is not None

    rotated = ("G", "Am", "F", "C")
    broken_hypothesis = [
        (start, end, rotated[LABELS.index(label)]) for start, end, label in hypothesis
    ]
    broken = score_take(reference, broken_hypothesis)
    assert broken["csr"] < 0.2
    assert broken["csr"] < good["csr"]
    assert broken["change_f1"] == pytest.approx(good["change_f1"])


# --------------------------------------------------------------------------- #
# The script over a synthetic corpus
# --------------------------------------------------------------------------- #
def test_harness_pins_and_measures_a_synthetic_corpus(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    jams_path = _write_corpus(corpus)
    manifest = tmp_path / "manifest.json"

    pinned = _run("--corpus-dir", str(corpus), "--write-manifest", str(manifest))
    assert pinned.returncode == 0, pinned.stderr
    document = json.loads(manifest.read_text(encoding="utf-8"))
    assert document["license"] == "CC BY 4.0"
    assert document["dataset"] == "GuitarSet"
    assert len(document["takes"]) == 1
    take = document["takes"][0]
    assert take["name"] == "01_Demo_comp"
    assert take["duration_seconds"] == pytest.approx(DURATION, abs=0.01)
    assert (
        take["audio_sha256"]
        == hashlib.sha256((corpus / "01_Demo_comp_mic.wav").read_bytes()).hexdigest()
    )
    assert take["jams_sha256"] == hashlib.sha256(jams_path.read_bytes()).hexdigest()

    out = tmp_path / "out"
    measured = _run(
        "--manifest",
        str(manifest),
        "--corpus-dir",
        str(corpus),
        "--out",
        str(out),
        "--limit",
        "1",
    )
    assert measured.returncode == 0, measured.stderr
    rows = [
        json.loads(line)
        for line in (out / "per_take.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 1
    row = rows[0]
    assert row["take"] == "01_Demo_comp"
    assert row["reference"] == "instructed"
    assert row["csr"] > 0.9
    assert row["decoder"] == "viterbi"
    assert row["peak_rss_bytes"] is None or row["peak_rss_bytes"] > 0
    # Every event the engine reports now carries a confidence, and the row
    # records the calibration table it feeds.
    assert row["confidence"]["events"] > 0
    assert row["confidence"]["unknown_events"] == 0

    aggregate = json.loads((out / "aggregate.json").read_text(encoding="utf-8"))
    assert aggregate["metrics"]["count"] == 1
    assert aggregate["settings"]["reference"] == "instructed"
    assert aggregate["manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert aggregate["environment"]["engine"] == "chroma-baseline"
    assert aggregate["date"]
    assert aggregate["confidence"]["accuracy"] is not None
    assert aggregate["confidence"]["brier"] is not None
    report = (out / "aggregate.md").read_text(encoding="utf-8")
    assert "Duration CSR (raw)" in report
    assert "reference view `instructed`" in report
    assert "### Confidence calibration" in report
    assert "### Risk–coverage" in report


def test_harness_refuses_bytes_that_do_not_match_the_manifest(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    _write_corpus(corpus)
    manifest = tmp_path / "manifest.json"
    assert _run("--corpus-dir", str(corpus), "--write-manifest", str(manifest)).returncode == 0
    with (corpus / "01_Demo_comp_mic.wav").open("ab") as handle:
        handle.write(b"\x00\x00")

    out = tmp_path / "out"
    result = _run(
        "--manifest", str(manifest), "--corpus-dir", str(corpus), "--out", str(out), "--limit", "1"
    )
    assert result.returncode == 2
    assert "does not match the manifest" in result.stderr
    # No row may be written for a take that failed verification.
    jsonl = out / "per_take.jsonl"
    assert not jsonl.exists() or jsonl.read_text(encoding="utf-8") == ""


def test_harness_refits_the_confidence_mapping(tmp_path: Path) -> None:
    """The mapping's provenance is reproducible from the corpus, not asserted."""
    corpus = tmp_path / "corpus"
    # The training take (index 0) has two chords annotated wrong, so the fit
    # sees both correct and incorrect events; the held-out take is clean.
    _write_corpus(corpus, harte=("C:maj", "A:min", "G:maj", "F:maj"))
    _write_corpus(corpus, name="02_Demo_comp")
    manifest = tmp_path / "manifest.json"
    assert _run("--corpus-dir", str(corpus), "--write-manifest", str(manifest)).returncode == 0

    out = tmp_path / "out"
    result = _run(
        "--manifest",
        str(manifest),
        "--corpus-dir",
        str(corpus),
        "--out",
        str(out),
        "--fit-confidence",
    )

    assert result.returncode == 0, result.stderr
    fit = json.loads((out / "confidence_fit.json").read_text(encoding="utf-8"))
    assert fit["train"]["takes"] == 1
    assert fit["heldout"]["takes"] == 1
    assert fit["train"]["events"] > 0
    assert fit["train"]["slope"] != 0.0
    assert fit["heldout"]["report"]["accuracy"] is not None
    assert fit["engine"]["slope"] == chroma_baseline.CONFIDENCE_SLOPE
    assert fit["engine"]["intercept"] == chroma_baseline.CONFIDENCE_INTERCEPT
    assert "confidence fit" in result.stdout


def test_harness_forwards_engine_options_and_records_them(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    _write_corpus(corpus)
    manifest = tmp_path / "manifest.json"
    assert _run("--corpus-dir", str(corpus), "--write-manifest", str(manifest)).returncode == 0

    out = tmp_path / "out"
    measured = _run(
        "--manifest",
        str(manifest),
        "--corpus-dir",
        str(corpus),
        "--out",
        str(out),
        "--option",
        "tuning=auto",
        "--option",
        "harmonic=true",
    )

    assert measured.returncode == 0, measured.stderr
    aggregate = json.loads((out / "aggregate.json").read_text(encoding="utf-8"))
    assert aggregate["settings"]["engine_options"] == {"tuning": "auto", "harmonic": True}
    row = json.loads((out / "per_take.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert row["decoder"] == "viterbi"  # the flags keep their defaults
    report = (out / "aggregate.md").read_text(encoding="utf-8")
    assert "`tuning=auto`" in report
    assert "`harmonic=true`" in report


def test_harness_refuses_an_option_that_is_not_key_value(tmp_path: Path) -> None:
    result = _run("--option", "tuning", "--out", str(tmp_path / "out"))

    assert result.returncode == 2
    assert "not KEY=VALUE" in result.stderr


def test_fit_confidence_refuses_to_resume_a_run(tmp_path: Path) -> None:
    result = _run("--fit-confidence", "--resume", "--out", str(tmp_path / "out"))

    assert result.returncode == 2
    assert "--fit-confidence cannot resume" in result.stderr


def test_harness_refuses_a_missing_take(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    _write_corpus(corpus)
    manifest = tmp_path / "manifest.json"
    assert _run("--corpus-dir", str(corpus), "--write-manifest", str(manifest)).returncode == 0
    (corpus / "01_Demo_comp_mic.wav").unlink()

    result = _run(
        "--manifest", str(manifest), "--corpus-dir", str(corpus), "--out", str(tmp_path / "out")
    )
    assert result.returncode == 2
    assert "audio file not found" in result.stderr
    assert "10.5281/zenodo.3371780" in result.stderr
