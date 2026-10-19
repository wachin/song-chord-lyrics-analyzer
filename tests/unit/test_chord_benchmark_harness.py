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
from song_chord_lyrics_analyzer.engines import ChromaBaselineEngine
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


def _write_corpus(corpus_dir: Path) -> Path:
    """A one-take corpus: ``01_Demo_comp_mic.wav`` plus its JAMS reference."""
    corpus_dir.mkdir(parents=True, exist_ok=True)
    write_chord_wav(
        corpus_dir / "01_Demo_comp_mic.wav",
        chords=PROGRESSION,
        seconds_per_chord=SECONDS_PER_CHORD,
    )
    jams = {
        "annotations": [
            {
                "namespace": "chord",
                "data": [
                    {"time": start, "duration": end - start, "value": value}
                    for (start, end, _label), value in zip(_reference(), HARTE, strict=True)
                ],
            }
        ]
    }
    path = corpus_dir / "01_Demo_comp.jams"
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

    aggregate = json.loads((out / "aggregate.json").read_text(encoding="utf-8"))
    assert aggregate["metrics"]["count"] == 1
    assert aggregate["settings"]["reference"] == "instructed"
    assert aggregate["manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert aggregate["environment"]["engine"] == "chroma-baseline"
    assert aggregate["date"]
    report = (out / "aggregate.md").read_text(encoding="utf-8")
    assert "Duration CSR (raw)" in report
    assert "reference view `instructed`" in report


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
