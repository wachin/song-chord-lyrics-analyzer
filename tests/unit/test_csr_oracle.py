"""CSR oracle fixture tests (roadmap section 44): scoring semantics are pinned.

``tests/fixtures/csr_oracle.json`` records, for 22 GuitarSet comping takes,
both chord annotations (instructed / performed) as raw Harte observations plus
the v2-default hypothesis segmentation, with the expected duration-CSR numbers
for four views (raw / triad-reduced x each annotation). The expected values
were measured by the original harness on 2026-09-29 and re-verified after the
scoring semantics moved into the package (2026-10-01, 88/88 targets); these
tests keep the semantics from drifting. Dataset provenance (GuitarSet,
CC BY 4.0) is recorded inside the fixture itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from song_chord_lyrics_analyzer.evaluation import (
    chord_pcs,
    duration_csr,
    harte_to_label,
    mirex_equal,
    reduce_ref_view,
    triad_reduce,
)

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "csr_oracle.json"
ORACLE = json.loads(FIXTURE.read_text(encoding="utf-8"))
TAKES = ORACLE["takes"]
TOL = ORACLE["tolerance"]


def _ref_segments(take: dict, k: int) -> list[tuple[float, float, str]]:
    """Rebuild timed reference segments: Harte observations -> canonical labels."""
    observations = take["refs"][k]
    labels = [harte_to_label(obs[2]) for obs in observations]
    return [
        (float(start), float(end), label)
        for (start, end, _), label in zip(observations, labels, strict=True)
    ]


def _hyp_segments(take: dict) -> list[tuple[float, float, str]]:
    return [(float(start), float(end), label) for start, end, label in take["hyp"]]


@pytest.mark.parametrize("take_name", sorted(TAKES))
@pytest.mark.parametrize("k", [0, 1], ids=["instructed", "performed"])
@pytest.mark.parametrize(("view", "reduced"), [("raw", False), ("triads", True)])
class TestOracleViews:
    def test_duration_csr_matches_oracle(
        self, take_name: str, k: int, view: str, reduced: bool
    ) -> None:
        take = TAKES[take_name]
        ref = _ref_segments(take, k)
        if reduced:
            ref = reduce_ref_view(ref)
        got = duration_csr(ref, _hyp_segments(take))
        expected = take["expected"][f"r{k}_{view}"]
        assert got["csr"] == pytest.approx(expected["csr"], abs=TOL["csr_abs"])
        assert got["equal_s"] == pytest.approx(expected["equal_s"], abs=TOL["equal_s_abs"])
        assert got["total_s"] == pytest.approx(expected["total_s"], abs=TOL["equal_s_abs"])


class TestMirexEqualRules:
    """Corner rules the oracle forced; do not simplify them away."""

    def test_degree_bass_rescue(self) -> None:
        # D# major triad vs D# minor: intersection {D#, A#} == 2, rescued
        # because the reference's Harte degree slash (5 = the fifth) sounds
        # inside the minor triad.
        assert mirex_equal("D#/5", "D#m") == 1.0

    def test_direct_bass_rescue(self) -> None:
        # C/E vs Am: intersection {C, E} == 2, rescued because the reference's
        # non-root bass note E sounds inside Am; the reference-bass bonus then
        # stacks on top (1.0 rescue + 1.0 bass bonus).
        assert mirex_equal("C/E", "Am") == 2.0

    def test_rescue_denied_when_bass_is_root_degree(self) -> None:
        # F/1 (Harte degree 1 = the root itself) vs Fm: no non-root bass, no
        # rescue despite the {F, A#}... {F, C} intersection of 2.
        assert mirex_equal("F/1", "Fm") == 0.0

    def test_rescue_denied_when_bass_absent_from_hypothesis(self) -> None:
        # C/E vs Cm: E is not inside Cm, so the rescue fails and the score is
        # exactly 0.0 — the hyp bass bonus must not resurrect a failed rescue.
        assert mirex_equal("C/E", "Cm") == 0.0

    def test_tuple_voicing_opts_out_of_rescue(self) -> None:
        # D:(1,5)/5 vs D: bracketed tuples replace the voicing and opt out of
        # the bass rescue, so the intersection of 2 stays a mismatch.
        assert mirex_equal("D(1,5)/5", "D") == 0.0

    def test_augmented_reference_matches_from_two(self) -> None:
        assert mirex_equal("Caug", "C") == 1.0

    def test_no_chord_matches_only_no_chord(self) -> None:
        assert mirex_equal("N", "N") == 1.0
        assert mirex_equal("N", "C") == 0.0
        assert mirex_equal("C", "N") == 0.0

    def test_exact_match_with_foreign_bass_bonuses(self) -> None:
        # Same pitch classes plus each side's non-root bass sounding inside
        # the other chord: 1.0 + 1.0 + 1.0.
        assert mirex_equal("C/E", "Am/C") == 3.0


class TestTriadReduceRules:
    def test_minor_keeps_m_spelling(self) -> None:
        # Exact-minor heads keep their `m` spelling, brackets/slashes stripped.
        assert triad_reduce(["Bm(4)", "Am", "C#m/F#"]) == ["Bm", "Am", "C#m"]

    def test_everything_else_collapses_to_root(self) -> None:
        # Out-of-enum spellings included: the 04_Jazz2 oracle case forced
        # A#m11 -> A#. Extended minors (m7, m11) are NOT the MINOR quality,
        # so they collapse to the bare root too — the oracle pinned this.
        assert triad_reduce(["E5", "Ehdim7", "A#m11", "Fm7", "Bmaj6(#9)"]) == [
            "E",
            "E",
            "A#",
            "F",
            "B",
        ]

    def test_no_chord_and_unparsable(self) -> None:
        assert triad_reduce(["N"]) == ["N"]
        assert triad_reduce(["xx"]) == ["xx"]  # unparsable stays intact

    def test_timed_view(self) -> None:
        assert reduce_ref_view([(0.0, 1.0, "A#m11")]) == [(0.0, 1.0, "A#")]


class TestHarteToLabel:
    @pytest.mark.parametrize(
        ("harte", "expected"),
        [
            ("Bb:min7", "A#m7"),
            ("F#:7/5", "F#7/5"),
            ("A:maj", "A"),
            ("A:min/5", "Am/5"),
            ("C#:hdim7/1", "C#hdim7/1"),
            ("N", "N"),
        ],
    )
    def test_spelling_map(self, harte: str, expected: str) -> None:
        assert harte_to_label(harte) == expected


class TestChordPcs:
    def test_major_triad(self) -> None:
        pcs, root, bass = chord_pcs("C")
        assert pcs == frozenset({0, 4, 7})
        assert root == 0
        assert bass is None

    def test_degree_bass_is_not_a_slash_note(self) -> None:
        # A/5 stores no bass note (degree slashes parse as extension text);
        # the decoder recovers the sounding bass via _bass_pc at scoring time.
        pcs, root, bass = chord_pcs("A/5")
        assert pcs == frozenset({9, 1, 4})
        assert root == 9
        assert bass is None

    def test_tuple_replaces_base_voicing(self) -> None:
        # Bracketed tuple (1,5) replaces the major triad: root+fifth only.
        pcs, root, _ = chord_pcs("D(1,5)/5")
        assert pcs == frozenset({2, 9})
        assert root == 2

    def test_no_chord(self) -> None:
        pcs, root, bass = chord_pcs("N")
        assert pcs == frozenset()
        assert root is None
        assert bass is None


class TestDurationCsr:
    def test_empty_reference(self) -> None:
        assert duration_csr([], [(0.0, 1.0, "C")]) == {
            "csr": 0.0,
            "equal_s": 0.0,
            "total_s": 0.0,
        }

    def test_identical_segmentations_score_one(self) -> None:
        segs = [(0.0, 2.0, "C"), (2.0, 4.0, "G")]
        assert duration_csr(segs, segs)["csr"] == 1.0

    def test_no_chord_agreement_counts(self) -> None:
        segs = [(0.0, 2.0, "N"), (2.0, 4.0, "C")]
        got = duration_csr(segs, [(0.0, 4.0, "N")])
        assert got["equal_s"] == 2.0
        assert got["total_s"] == 4.0


class TestFixtureVocabulary:
    """Every recorded label must decode to a non-empty pitch-class set."""

    @pytest.mark.parametrize("side", ["refs", "hyp"])
    def test_all_recorded_labels_decode(self, side: str) -> None:
        for take in TAKES.values():
            if side == "refs":
                labels = [harte_to_label(obs[2]) for ann in take["refs"] for obs in ann]
            else:
                labels = [label for _, _, label in take["hyp"]]
            assert labels
            for label in labels:
                pcs, root, _ = chord_pcs(label)
                if label == "N":
                    continue
                assert root is not None, f"{label} failed to decode a root"
                if not pcs:
                    # Only a voicing tuple that omits every tone (the v2
                    # decoder emitted E9(*1)/3) decodes to an empty set; such
                    # a label can only match itself under mirex_equal.
                    assert "(" in label, f"{label} decoded to an empty pitch-class set"

    def test_provenance_records_dataset_licence(self) -> None:
        assert "GuitarSet" in ORACLE["provenance"]["dataset"]
        assert "CC BY 4.0" in ORACLE["provenance"]["dataset"]
