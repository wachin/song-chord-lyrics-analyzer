"""GuitarSet corpus tests (Phase I P1).

Two jobs:

* pin the committed manifest as the fixed reference set — 180 comp takes, each
  with both SHA-256 digests — so the measured corpus cannot drift silently;
* pin the scoring vector and the JAMS reader, including the failure modes that
  would otherwise turn a wrong corpus into a plausible number.

Every reference here is hand-written or a synthetic JAMS in ``tmp_path``; no
downloaded dataset is required, so this module runs in CI without audio.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from song_chord_lyrics_analyzer.evaluation.guitarset import (
    aggregate_scores,
    load_manifest,
    read_jams_chords,
    score_take,
    sha256_file,
    verify_take_files,
)
from song_chord_lyrics_analyzer.utils.errors import InputError

MANIFEST = Path(__file__).resolve().parents[1] / "fixtures" / "guitarset_comp_manifest.json"


def _document(takes: list[dict]) -> dict:
    """A manifest skeleton around the given takes."""
    return {
        "dataset": "GuitarSet",
        "version": "1.1.0",
        "doi": "10.5281/zenodo.3371780",
        "license": "CC BY 4.0",
        "retrieved": "2026-09-29",
        "notes": "test fixture",
        "takes": takes,
    }


def _take(name: str = "00_Test_comp", **overrides) -> dict:
    """One well-formed manifest take."""
    take = {
        "name": name,
        "split": "comp",
        "audio": f"{name}_mic.wav",
        "jams": f"{name}.jams",
        "audio_sha256": "a" * 64,
        "jams_sha256": "b" * 64,
        "duration_seconds": 10.0,
    }
    take.update(overrides)
    return take


def _write(tmp_path: Path, document: dict, name: str = "manifest.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _jams(annotations: list[dict]) -> dict:
    """A minimal JAMS document with the given annotations."""
    return {"annotations": annotations}


def _chord_annotation(values: list[tuple[float, float, str]]) -> dict:
    return {
        "namespace": "chord",
        "data": [
            {"time": start, "duration": duration, "value": value}
            for start, duration, value in values
        ],
    }


# --------------------------------------------------------------------------- #
# The committed manifest
# --------------------------------------------------------------------------- #
def test_committed_manifest_pins_180_comp_takes() -> None:
    """The measured corpus is fixed: changing it must be a deliberate edit."""
    manifest = load_manifest(MANIFEST)
    assert manifest.dataset == "GuitarSet"
    assert manifest.version == "1.1.0"
    assert manifest.doi == "10.5281/zenodo.3371780"
    assert manifest.license == "CC BY 4.0"
    assert len(manifest.takes) == 180
    assert [take.name for take in manifest.takes] == sorted(take.name for take in manifest.takes)
    assert {take.split for take in manifest.takes} == {"comp"}
    assert all(take.audio.endswith("_mic.wav") for take in manifest.takes)
    assert all(take.jams.endswith(".jams") for take in manifest.takes)
    assert all(
        len(take.audio_sha256) == 64 and len(take.jams_sha256) == 64 for take in manifest.takes
    )
    # GuitarSet comp takes are 14-46 s each; the pinned corpus is ~91 minutes.
    assert all(10.0 < take.duration_seconds < 60.0 for take in manifest.takes)
    assert 5000.0 < sum(take.duration_seconds for take in manifest.takes) < 6000.0


def test_manifest_subset_and_lookup() -> None:
    manifest = load_manifest(MANIFEST)
    assert manifest.by_name(manifest.takes[0].name) is manifest.takes[0]
    assert len(manifest.subset(split="comp")) == 180
    with pytest.raises(InputError, match="no 'solo' takes"):
        manifest.subset(split="solo")
    with pytest.raises(InputError, match="not in the GuitarSet manifest"):
        manifest.by_name("not-a-take")


def test_manifest_rejects_duplicate_takes(tmp_path: Path) -> None:
    document = _document([_take(), _take()])
    with pytest.raises(InputError, match="lists takes more than once"):
        load_manifest(_write(tmp_path, document))


def test_manifest_rejects_malformed_digest(tmp_path: Path) -> None:
    document = _document([_take(audio_sha256="not-a-digest")])
    with pytest.raises(InputError, match="not a SHA-256 hex digest"):
        load_manifest(_write(tmp_path, document))


def test_manifest_rejects_absolute_paths(tmp_path: Path) -> None:
    document = _document([_take(audio="/abs/path.wav")])
    with pytest.raises(InputError, match="absolute path"):
        load_manifest(_write(tmp_path, document))


def test_manifest_rejects_unknown_split_and_missing_duration(tmp_path: Path) -> None:
    with pytest.raises(InputError, match="split"):
        load_manifest(_write(tmp_path, _document([_take(split="duet")]), "a.json"))
    with pytest.raises(InputError, match="duration_seconds"):
        load_manifest(_write(tmp_path, _document([_take(duration_seconds=0)]), "b.json"))


def test_manifest_rejects_missing_provenance_and_empty_takes(tmp_path: Path) -> None:
    document = _document([_take()])
    del document["license"]
    with pytest.raises(InputError, match="'license'"):
        load_manifest(_write(tmp_path, document, "a.json"))
    with pytest.raises(InputError, match="has no takes"):
        load_manifest(_write(tmp_path, _document([]), "b.json"))


def test_manifest_missing_file_names_the_path(tmp_path: Path) -> None:
    with pytest.raises(InputError, match="manifest not found"):
        load_manifest(tmp_path / "absent.json")


# --------------------------------------------------------------------------- #
# File verification
# --------------------------------------------------------------------------- #
def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    path = tmp_path / "payload.bin"
    path.write_bytes(b"guitarset-check" * 1000)
    assert sha256_file(path) == hashlib.sha256(path.read_bytes()).hexdigest()


def test_verify_take_files_accepts_matching_bytes(tmp_path: Path) -> None:
    audio = tmp_path / "00_Test_comp_mic.wav"
    jams = tmp_path / "00_Test_comp.jams"
    audio.write_bytes(b"audio")
    jams.write_text("{}", encoding="utf-8")
    document = _document(
        [
            _take(
                audio_sha256=hashlib.sha256(b"audio").hexdigest(),
                jams_sha256=hashlib.sha256(b"{}").hexdigest(),
            )
        ]
    )
    take = load_manifest(_write(tmp_path, document)).takes[0]
    assert verify_take_files(take, tmp_path) == (audio, jams)
    # check_hashes=False must not read the files at all.
    assert verify_take_files(take, tmp_path, check_hashes=False) == (audio, jams)


def test_verify_take_files_refuses_a_different_byte_stream(tmp_path: Path) -> None:
    (tmp_path / "00_Test_comp_mic.wav").write_bytes(b"different audio")
    (tmp_path / "00_Test_comp.jams").write_bytes(b"b" * 32)
    take = load_manifest(_write(tmp_path, _document([_take()]))).takes[0]
    with pytest.raises(InputError, match="does not match the manifest"):
        verify_take_files(take, tmp_path)


def test_verify_take_files_missing_audio_hints_at_the_download(tmp_path: Path) -> None:
    take = load_manifest(_write(tmp_path, _document([_take()]))).takes[0]
    with pytest.raises(InputError, match="audio file not found") as raised:
        verify_take_files(take, tmp_path)
    assert "10.5281/zenodo.3371780" in (raised.value.hint or "")


# --------------------------------------------------------------------------- #
# JAMS reading
# --------------------------------------------------------------------------- #
def test_read_jams_chords_converts_harte_and_drops_empty_observations(tmp_path: Path) -> None:
    path = tmp_path / "take.jams"
    path.write_text(
        json.dumps(
            _jams(
                [
                    _chord_annotation(
                        [
                            (0.0, 2.0, "Bb:min7"),
                            (2.0, 0.0, "C:maj"),
                            (2.0, 2.0, "C:maj"),
                            (4.0, 2.0, "N"),
                        ]
                    ),
                    _chord_annotation([(0.0, 6.0, "F#:7/5")]),
                ]
            )
        ),
        encoding="utf-8",
    )
    assert read_jams_chords(path) == [(0.0, 2.0, "A#m7"), (2.0, 4.0, "C"), (4.0, 6.0, "N")]
    assert read_jams_chords(path, index=1) == [(0.0, 6.0, "F#7/5")]


def test_read_jams_chords_rejects_a_document_without_chords(tmp_path: Path) -> None:
    path = tmp_path / "take.jams"
    path.write_text(json.dumps(_jams([{"namespace": "beat", "data": []}])), encoding="utf-8")
    with pytest.raises(InputError, match="no chord annotation"):
        read_jams_chords(path)


def test_read_jams_chords_rejects_an_index_past_the_annotations(tmp_path: Path) -> None:
    path = tmp_path / "take.jams"
    path.write_text(json.dumps(_jams([_chord_annotation([(0.0, 1.0, "C")])])), encoding="utf-8")
    with pytest.raises(InputError, match="not index 1"):
        read_jams_chords(path, index=1)


def test_read_jams_chords_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "take.jams"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(InputError, match="not valid JSON"):
        read_jams_chords(path)


# --------------------------------------------------------------------------- #
# Scoring vector
# --------------------------------------------------------------------------- #
def test_score_take_rewards_an_exact_reference() -> None:
    reference = [(0.0, 2.0, "C"), (2.0, 4.0, "Am")]
    score = score_take(reference, reference)
    assert score["csr"] == pytest.approx(1.0)
    assert score["csr_triads"] == pytest.approx(1.0)
    assert score["segment_overlap"] == pytest.approx(1.0)
    assert score["change_f1"] == pytest.approx(1.0)
    assert score["timing_reference_to_hypothesis"] == pytest.approx(0.0)
    assert score["reference_chords"] == 2
    assert score["hypothesis_chords"] == 2


def test_score_take_duration_weights_a_split_hypothesis() -> None:
    """The CSR case from the metrics suite: 11 of 16 reference seconds match."""
    reference = [(0.0, 6.0, "C"), (6.0, 16.0, "G")]
    hypothesis = [(0.0, 6.0, "C"), (6.0, 11.0, "G"), (11.0, 16.0, "Am")]
    assert score_take(reference, hypothesis)["csr"] == pytest.approx(11 / 16)


def test_score_take_triad_view_can_pass_where_the_raw_label_fails() -> None:
    """A sus4 reference is not MIREX-equal to the plain triad, but reduces to it."""
    reference = [(0.0, 4.0, "Csus4")]
    hypothesis = [(0.0, 4.0, "C")]
    score = score_take(reference, hypothesis)
    assert score["csr"] == pytest.approx(0.0)
    assert score["csr_triads"] == pytest.approx(1.0)


def test_score_take_counts_a_wrong_hypothesis_as_a_miss() -> None:
    """Nothing is dropped: the time a wrong label occupies lowers the CSR."""
    reference = [(0.0, 4.0, "C")]
    hypothesis = [(0.0, 2.0, "C"), (2.0, 4.0, "D")]
    score = score_take(reference, hypothesis)
    assert score["csr"] == pytest.approx(0.5)
    assert score["hypothesis_chords"] == 2


def test_score_take_reports_no_timing_when_a_side_is_empty() -> None:
    score = score_take([(0.0, 2.0, "C")], [])
    assert score["csr"] == pytest.approx(0.0)
    assert score["timing_reference_to_hypothesis"] is None
    assert score["timing_hypothesis_to_reference"] is None
    assert score["change_f1"] == pytest.approx(0.0)


def test_aggregate_scores_averages_only_what_exists() -> None:
    rows = [
        {"csr": 0.5, "csr_triads": 0.4, "hypothesis_chords": 5, "reference_chords": 4},
        {"csr": 1.0, "csr_triads": 0.8, "hypothesis_chords": 7, "reference_chords": 4},
        {"csr": None, "hypothesis_chords": 6, "reference_chords": 4},
    ]
    summary = aggregate_scores(rows)
    assert summary["count"] == 3
    assert summary["csr"]["mean"] == pytest.approx(0.75)
    assert summary["csr"]["min"] == pytest.approx(0.5)
    assert summary["csr_triads"]["median"] == pytest.approx(0.6)
    assert "timing_reference_to_hypothesis" not in summary
    assert summary["reference_chords"]["total"] == 12


def test_aggregate_scores_of_nothing_is_empty() -> None:
    assert aggregate_scores([]) == {}
