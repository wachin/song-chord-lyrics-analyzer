"""Unit tests for the chroma template baseline engine (roadmap sections 14 and 59).

The first concrete engine behind the ``ChordEngine`` protocol. The decoding
pipeline's dependency-free half (template matching, smoothing, segmentation)
is tested directly; the librosa front end is exercised only when the optional
DSP stack is installed, exactly as :meth:`ChromaBaselineEngine.is_available`
promises.
"""

from __future__ import annotations

from itertools import pairwise

import pytest

from fixtures.audio import write_sine_wav
from song_chord_lyrics_analyzer.engines import ChromaBaselineEngine, EngineKind
from song_chord_lyrics_analyzer.engines import chroma_baseline as baseline
from song_chord_lyrics_analyzer.engines.base import ChordAnalysisOptions
from song_chord_lyrics_analyzer.models.music import (
    PITCH_CLASS_NAMES,
    ChordQuality,
)
from song_chord_lyrics_analyzer.utils.errors import (
    AudioFileNotFoundError,
    DependencyError,
    InputError,
)

ENGINE = ChromaBaselineEngine()


def _frame(pitch_classes: tuple[int, ...]) -> list[float]:
    """A chroma frame with 1.0 on the given pitch classes and 0.0 elsewhere."""
    vector = [0.0] * 12
    for index in pitch_classes:
        vector[index] = 1.0
    return vector


def _bins(template: tuple[float, ...]) -> list[int]:
    return [index for index, value in enumerate(template) if value]


class TestTemplates:
    def test_twenty_four_phase_one_labels(self) -> None:
        assert len(baseline.TEMPLATE_LABELS) == 24
        assert baseline.TEMPLATE_LABELS[:12] == tuple(PITCH_CLASS_NAMES)
        assert baseline.TEMPLATE_LABELS[12:] == tuple(f"{root}m" for root in PITCH_CLASS_NAMES)

    def test_every_template_is_a_three_note_triad(self) -> None:
        assert len(baseline.TEMPLATES) == 24
        assert all(sum(template) == 3.0 for template in baseline.TEMPLATES)

    def test_c_major_template_sits_on_c_e_g(self) -> None:
        assert _bins(baseline.TEMPLATES[0]) == [0, 4, 7]

    def test_a_minor_template_sits_on_a_c_e(self) -> None:
        a_minor = baseline.TEMPLATES[12 + PITCH_CLASS_NAMES.index("A")]
        assert _bins(a_minor) == [0, 4, 9]


class TestMatchFrames:
    def test_pure_major_frame_matches_its_major_label(self) -> None:
        frame = _frame((0, 4, 7))  # C E G
        assert baseline.match_frames([frame]) == ["C"]

    def test_pure_minor_frame_matches_its_minor_label(self) -> None:
        frame = _frame((9, 0, 4))  # A C E
        assert baseline.match_frames([frame]) == ["Am"]

    def test_silent_frame_is_reported_as_no_chord(self) -> None:
        assert baseline.match_frames([[0.0] * 12]) == ["N"]

    def test_low_evidence_frame_is_not_forced_onto_a_chord(self) -> None:
        # A semitone dyad fits no triad: the best template reaches only one
        # of its three bins, so cosine similarity stays below the threshold.
        frame = _frame((0, 1))
        assert baseline.match_frames([frame]) == ["N"]

    def test_threshold_decides_between_chord_and_no_chord(self) -> None:
        # C E G plus a passing tone: good enough for the default threshold...
        frame = _frame((0, 4, 6, 7))
        assert baseline.match_frames([frame]) == ["C"]
        # ...but not for a stricter one, which reports the uncertainty.
        assert baseline.match_frames([frame], threshold=0.99) == ["N"]

    def test_one_label_per_frame_in_order(self) -> None:
        frames = [_frame((0, 4, 7)), [0.0] * 12, _frame((9, 0, 4))]
        assert baseline.match_frames(frames) == ["C", "N", "Am"]

    def test_frame_with_wrong_length_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            baseline.match_frames([[1.0] * 11])


class TestSmoothLabels:
    def test_isolated_flip_inside_a_run_is_removed(self) -> None:
        labels = ["C", "C", "C", "G", "C", "C", "C"]
        assert baseline.smooth_labels(labels, width=5) == ["C"] * 7

    def test_a_long_boundary_is_kept_where_it_is(self) -> None:
        labels = ["C"] * 4 + ["G"] * 4
        assert baseline.smooth_labels(labels, width=5) == labels

    def test_width_one_returns_the_sequence_unchanged(self) -> None:
        labels = ["C", "G", "C"]
        assert baseline.smooth_labels(labels, width=1) == labels

    def test_empty_sequence_stays_empty(self) -> None:
        assert baseline.smooth_labels([], width=5) == []


class TestFrameScores:
    def test_one_score_per_triad_plus_a_no_chord_state(self) -> None:
        scores = baseline.frame_scores([_frame((0, 4, 7))])
        assert len(scores) == 1
        assert len(scores[0]) == 25
        assert scores[0][-1] == baseline.DEFAULT_NO_CHORD_SCORE

    def test_a_pure_triad_scores_one_on_its_template(self) -> None:
        scores = baseline.frame_scores([_frame((0, 4, 7))])[0]
        assert scores[baseline.TEMPLATE_LABELS.index("C")] == pytest.approx(1.0)

    def test_a_silent_frame_scores_zero_on_every_triad(self) -> None:
        scores = baseline.frame_scores([[0.0] * 12])[0]
        assert scores[:24] == [0.0] * 24

    def test_no_chord_score_is_configurable(self) -> None:
        scores = baseline.frame_scores([[0.0] * 12], no_chord_score=0.25)
        assert scores[0][-1] == 0.25


class TestDecodeLabels:
    def test_majority_matches_the_per_frame_baseline(self) -> None:
        frames = [_frame((0, 4, 7)), [0.0] * 12, _frame((9, 0, 4))]
        expected = baseline.smooth_labels(baseline.match_frames(frames))
        assert baseline.decode_labels(frames, decoder="majority") == expected

    def test_viterbi_returns_one_known_label_per_frame(self) -> None:
        frames = [_frame((0, 4, 7)), [0.0] * 12, _frame((9, 0, 4))]
        labels = baseline.decode_labels(frames, decoder="viterbi")
        assert len(labels) == len(frames)
        assert all(label in baseline.TEMPLATE_LABELS or label == "N" for label in labels)

    def test_zero_penalty_viterbi_is_the_argmax_over_all_states(self) -> None:
        frames = [_frame((0, 4, 7)), [0.0] * 12, _frame((9, 0, 4))]
        scores = baseline.frame_scores(frames)
        expected = []
        for row in scores:
            best = row.index(max(row))
            expected.append(baseline.TEMPLATE_LABELS[best] if best < 24 else "N")
        assert baseline.decode_labels(frames, decoder="viterbi", change_penalty=0.0) == expected

    def test_unknown_decoder_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown decoder"):
            baseline.decode_labels([_frame((0, 4, 7))], decoder="magic")

    def test_negative_change_penalty_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="change_penalty"):
            baseline.decode_labels([_frame((0, 4, 7))], decoder="viterbi", change_penalty=-1.0)


class TestSegmentsFromLabels:
    def test_runs_collapse_into_timed_segments(self) -> None:
        segments = baseline.segments_from_labels(["C", "C", "G"], frame_period=0.5)
        assert segments == [(0.0, 1.0, "C"), (1.0, 1.5, "G")]

    def test_known_duration_clamps_the_last_end(self) -> None:
        segments = baseline.segments_from_labels(["C", "C", "G"], frame_period=0.5, duration=1.2)
        assert segments[-1] == (1.0, 1.2, "G")

    def test_duration_beyond_the_frame_grid_is_ignored(self) -> None:
        segments = baseline.segments_from_labels(["C"], frame_period=0.5, duration=10.0)
        assert segments == [(0.0, 0.5, "C")]

    def test_offset_shifts_every_boundary(self) -> None:
        segments = baseline.segments_from_labels(["C", "G"], frame_period=1.0, offset=5.0)
        assert segments == [(5.0, 6.0, "C"), (6.0, 7.0, "G")]

    def test_empty_labels_produce_no_segments(self) -> None:
        assert baseline.segments_from_labels([], frame_period=0.5) == []

    def test_non_positive_frame_period_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            baseline.segments_from_labels(["C"], frame_period=0.0)


class TestMergeShortSegments:
    def test_zero_minimum_returns_the_input(self) -> None:
        segments = [(0.0, 0.4, "C")]
        assert baseline.merge_short_segments(segments, minimum_duration=0.0) == segments

    def test_short_middle_segment_joins_its_neighbour(self) -> None:
        segments = [(0.0, 2.0, "C"), (2.0, 2.4, "G"), (2.4, 4.0, "C")]
        merged = baseline.merge_short_segments(segments, minimum_duration=0.5)
        assert merged == [(0.0, 4.0, "C")]

    def test_short_leading_segment_joins_the_next_one(self) -> None:
        segments = [(0.0, 0.4, "G"), (0.4, 3.0, "C")]
        merged = baseline.merge_short_segments(segments, minimum_duration=0.5)
        assert merged == [(0.0, 3.0, "C")]

    def test_all_short_segments_become_one(self) -> None:
        segments = [(0.0, 0.3, "C"), (0.3, 0.6, "G")]
        merged = baseline.merge_short_segments(segments, minimum_duration=0.5)
        assert merged == [(0.0, 0.6, "G")]

    def test_single_short_segment_stays_a_partition(self) -> None:
        segments = [(0.0, 0.4, "C")]
        assert baseline.merge_short_segments(segments, minimum_duration=0.5) == segments

    def test_long_segments_are_untouched(self) -> None:
        segments = [(0.0, 2.0, "C"), (2.0, 4.0, "G")]
        assert baseline.merge_short_segments(segments, minimum_duration=0.5) == segments


class TestMarginConfidence:
    def test_a_zero_margin_lands_near_the_middle_of_the_scale(self) -> None:
        assert 0.4 < baseline.margin_confidence(0.0) < 0.6

    def test_confidence_grows_with_the_margin(self) -> None:
        values = [baseline.margin_confidence(margin / 100.0) for margin in range(-20, 21)]
        assert all(later > earlier for earlier, later in pairwise(values))

    def test_extreme_margins_stay_inside_the_unit_interval(self) -> None:
        for margin in (-1e6, -1.0, 0.0, 1.0, 1e6):
            assert 0.0 <= baseline.margin_confidence(margin) <= 1.0

    def test_a_clean_triad_is_more_confident_than_a_noisy_one(self) -> None:
        clean = baseline.frame_scores([_frame((0, 4, 7))])
        noisy = baseline.frame_scores([_frame((0, 4, 6, 7))])
        clean_margin = baseline.segment_margins(
            clean, [(0.0, 1.0, "C")], frame_period=1.0, frame_count=1
        )[0]
        noisy_margin = baseline.segment_margins(
            noisy, [(0.0, 1.0, "C")], frame_period=1.0, frame_count=1
        )[0]

        assert clean_margin > noisy_margin
        assert baseline.margin_confidence(clean_margin) > baseline.margin_confidence(noisy_margin)


class TestSegmentMargins:
    def test_the_margin_is_the_winner_minus_the_runner_up(self) -> None:
        # C scores 1.0, G 0.5, the no-chord state 0.06: the C margin is 0.5.
        scores = [[0.0] * 25]
        scores[0][baseline.TEMPLATE_LABELS.index("C")] = 1.0
        scores[0][baseline.TEMPLATE_LABELS.index("G")] = 0.5
        scores[0][-1] = baseline.DEFAULT_NO_CHORD_SCORE

        margins = baseline.segment_margins(
            scores, [(0.0, 1.0, "C")], frame_period=1.0, frame_count=1
        )

        assert margins == [pytest.approx(0.5)]

    def test_no_chord_has_a_margin_too(self) -> None:
        scores = baseline.frame_scores([[0.0] * 12])

        margins = baseline.segment_margins(
            scores, [(0.0, 1.0, "N")], frame_period=1.0, frame_count=1
        )

        assert margins == [pytest.approx(baseline.DEFAULT_NO_CHORD_SCORE)]

    def test_a_kept_label_can_have_a_negative_margin(self) -> None:
        """Viterbi may keep a chord the frame itself preferred against."""
        scores = [[0.0] * 25]
        scores[0][baseline.TEMPLATE_LABELS.index("C")] = 0.2
        scores[0][baseline.TEMPLATE_LABELS.index("G")] = 0.9

        margins = baseline.segment_margins(
            scores, [(0.0, 1.0, "C")], frame_period=1.0, frame_count=1
        )

        assert margins == [pytest.approx(-0.7)]

    def test_the_mean_is_taken_over_the_segment_frames(self) -> None:
        scores = baseline.frame_scores([_frame((0, 4, 7)), _frame((0, 4, 7))])

        margins = baseline.segment_margins(
            scores, [(0.0, 2.0, "C")], frame_period=1.0, frame_count=2
        )

        assert len(margins) == 1
        assert margins[0] > 0.0

    def test_each_segment_reads_its_own_frames(self) -> None:
        quiet = baseline.frame_scores([_frame((0, 4, 7))])
        noisy = baseline.frame_scores([_frame((0, 4, 6, 7))])
        scores = [*quiet, *noisy]

        margins = baseline.segment_margins(
            scores,
            [(0.0, 1.0, "C"), (1.0, 2.0, "C")],
            frame_period=1.0,
            frame_count=2,
        )

        assert margins[0] > margins[1]

    def test_a_duration_clamped_last_end_does_not_drop_frames(self) -> None:
        scores = baseline.frame_scores([_frame((0, 4, 7)), _frame((0, 4, 7))])
        segments = baseline.segments_from_labels(["C", "C"], frame_period=1.0, duration=1.4)
        assert segments == [(0.0, 1.4, "C")]

        margins = baseline.segment_margins(scores, segments, frame_period=1.0, frame_count=2)

        unclamped = baseline.segment_margins(
            scores, [(0.0, 2.0, "C")], frame_period=1.0, frame_count=2
        )
        assert margins == unclamped

    def test_offset_shifts_the_frame_grid(self) -> None:
        scores = baseline.frame_scores([_frame((0, 4, 7)), [0.0] * 12])

        margins = baseline.segment_margins(
            scores,
            [(5.0, 6.0, "C"), (6.0, 7.0, "N")],
            frame_period=1.0,
            offset=5.0,
            frame_count=2,
        )

        assert margins[0] > margins[1]

    def test_no_segments_means_no_margins(self) -> None:
        scores = baseline.frame_scores([[0.0] * 12])

        assert baseline.segment_margins(scores, [], frame_period=1.0, frame_count=1) == []

    def test_a_segment_that_owns_no_frame_reports_no_evidence(self) -> None:
        scores = baseline.frame_scores([_frame((0, 4, 7))])

        margins = baseline.segment_margins(
            scores, [(0.0, 1.0, "C"), (0.0, 1.0, "G")], frame_period=1.0, frame_count=1
        )

        assert margins[0] == 0.0

    def test_an_unknown_label_is_rejected(self) -> None:
        scores = baseline.frame_scores([[0.0] * 12])
        with pytest.raises(ValueError, match="unknown chord label"):
            baseline.segment_margins(scores, [(0.0, 1.0, "H")], frame_period=1.0, frame_count=1)

    def test_a_non_positive_frame_period_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            baseline.segment_margins([], [], frame_period=0.0)

    def test_a_frame_count_outside_the_grid_is_rejected(self) -> None:
        scores = baseline.frame_scores([[0.0] * 12])
        with pytest.raises(ValueError, match="frame_count"):
            baseline.segment_margins(scores, [], frame_period=1.0, frame_count=2)


class TestEventsFromSegments:
    def test_major_minor_and_no_chord_become_canonical_events(self) -> None:
        events = baseline.events_from_segments(
            [(0.0, 2.0, "C"), (2.0, 4.0, "F#m"), (4.0, 6.0, "N")]
        )
        assert [event.label for event in events] == ["C", "F#m", "N"]
        assert events[0].root == "C"
        assert events[0].quality is ChordQuality.MAJOR
        assert events[1].root == "F#"
        assert events[1].quality is ChordQuality.MINOR
        assert events[2].quality is ChordQuality.NO_CHORD
        assert all(event.end is not None for event in events)

    def test_events_carry_the_engine_as_source(self) -> None:
        events = baseline.events_from_segments([(0.0, 1.0, "C")])
        assert events[0].source == "chroma-baseline"

    def test_a_margin_becomes_confidence_and_keeps_its_evidence(self) -> None:
        events = baseline.events_from_segments(
            [(0.0, 1.0, "C"), (1.0, 2.0, "N")], margins=[0.1, -0.2]
        )

        assert events[0].confidence.value == pytest.approx(baseline.margin_confidence(0.1))
        assert events[0].confidence.source == "chroma-baseline"
        assert events[0].metadata["score_margin"] == pytest.approx(0.1)
        # A claim of silence keeps its own evidence instead of losing it.
        assert events[1].confidence.value == pytest.approx(baseline.margin_confidence(-0.2))
        assert events[1].metadata["score_margin"] == pytest.approx(-0.2)

    def test_without_margins_confidence_is_unknown_not_zero(self) -> None:
        events = baseline.events_from_segments([(0.0, 1.0, "C")])

        assert events[0].confidence.is_known is False
        assert events[0].confidence.value is None
        assert events[0].metadata == {}

    def test_a_margin_count_mismatch_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="margins"):
            baseline.events_from_segments([(0.0, 1.0, "C")], margins=[0.1, 0.2])


class TestEngineContract:
    def test_identity(self) -> None:
        assert ENGINE.name == "chroma-baseline"
        assert ENGINE.kind is EngineKind.CHORDS

    def test_is_available_reports_a_plain_bool(self) -> None:
        assert isinstance(ENGINE.is_available(), bool)

    def test_engine_info_describes_capabilities(self) -> None:
        info = ENGINE.engine_info()
        assert info.name == "chroma-baseline"
        assert info.kind == "chords"
        assert info.version
        assert info.description and "chroma" in info.description
        assert info.license == "GPL-3.0-or-later"
        assert info.capabilities["vocabulary_phase"] == 1
        assert info.capabilities["confidence"] is True
        assert info.capabilities["confidence_method"] == "score_margin_logistic"

    def test_missing_audio_file_is_reported(self, tmp_path) -> None:
        with pytest.raises(AudioFileNotFoundError):
            ENGINE.analyze(tmp_path / "absent.wav", ChordAnalysisOptions())

    def test_later_vocabulary_phases_are_refused(self, tmp_path) -> None:
        wav = write_sine_wav(tmp_path / "tone.wav", seconds=0.5)
        with pytest.raises(InputError, match="phase 1"):
            ENGINE.analyze(wav, ChordAnalysisOptions(vocabulary_phase=2))

    def test_missing_dsp_stack_is_a_dependency_error(self, tmp_path, monkeypatch) -> None:
        wav = write_sine_wav(tmp_path / "tone.wav", seconds=0.5)

        def _unavailable() -> None:
            raise ImportError("no numpy here")

        monkeypatch.setattr(baseline, "_import_front_end", _unavailable)
        with pytest.raises(DependencyError, match="numpy and librosa") as excinfo:
            ENGINE.analyze(wav, ChordAnalysisOptions())
        assert "pip install" in str(excinfo.value)
        assert ENGINE.is_available() is False


@pytest.mark.skipif(
    not ENGINE.is_available(),
    reason="optional DSP stack (numpy/librosa) not installed",
)
class TestFullAnalysis:
    """End-to-end runs; executed only where the optional front end exists."""

    def test_analyze_returns_measured_honest_chords(self, tmp_path) -> None:
        wav = write_sine_wav(tmp_path / "tone.wav", seconds=3.0, frequency=440.0, channels=1)
        result = ENGINE.analyze(wav, ChordAnalysisOptions())

        assert result.engine == "chroma-baseline"
        assert result.chords, "the tone must produce at least one chord event"
        assert result.chords[0].start == 0.0
        assert result.chords[-1].end is not None
        assert result.chords[-1].end <= 3.1
        assert all(
            event.label in baseline.TEMPLATE_LABELS or event.label == "N" for event in result.chords
        )
        assert all(event.source == "chroma-baseline" for event in result.chords)

    def test_the_audio_comes_from_the_shared_decode_service(self, tmp_path, monkeypatch) -> None:
        """One decode owner, and the window the options describe (Phase A)."""
        wav = write_sine_wav(tmp_path / "tone.wav", seconds=1.0, channels=1)
        calls: list[dict[str, object]] = []
        decode = baseline.decode_audio

        def _recording_decode(path, **options):
            calls.append({"path": str(path), **options})
            return decode(path, **options)

        monkeypatch.setattr(baseline, "decode_audio", _recording_decode)
        ENGINE.analyze(wav, ChordAnalysisOptions(start=0.25, end=0.75))

        assert calls == [
            {
                "path": str(wav),
                "sample_rate": baseline.SAMPLE_RATE,
                "mono": True,
                "offset": 0.25,
                "duration": pytest.approx(0.5),
            }
        ]

    def test_run_cost_is_measured_not_estimated(self, tmp_path) -> None:
        wav = write_sine_wav(tmp_path / "tone.wav", seconds=2.0, channels=1)
        result = ENGINE.analyze(wav, ChordAnalysisOptions())

        assert result.processing_time_seconds is not None
        assert result.processing_time_seconds > 0.0
        performance = result.metadata["performance"]
        assert performance["audio_seconds"] == pytest.approx(2.0, abs=0.1)
        assert performance["real_time_factor"] > 0.0
        assert performance["device"] == "cpu"
        assert performance["vram_bytes"] is None  # a CPU run has no VRAM figure
        assert performance["peak_rss_bytes"] is None or performance["peak_rss_bytes"] > 0
        assert performance["startup_time_seconds"] is not None
        assert performance["startup_time_seconds"] >= 0.0
        # the untouched frame payload travels as raw output
        assert result.raw["frame_labels"]
        assert result.metadata["decoder"] == baseline.DEFAULT_DECODER
        assert result.metadata["change_penalty"] == baseline.DEFAULT_CHANGE_PENALTY

    def test_every_event_carries_a_measured_confidence(self, tmp_path) -> None:
        wav = write_sine_wav(tmp_path / "tone.wav", seconds=2.0, channels=1)
        result = ENGINE.analyze(wav, ChordAnalysisOptions())

        assert result.chords
        for event in result.chords:
            assert event.confidence.is_known, "the baseline must not report unknown any more"
            assert event.confidence.source == "chroma-baseline"
            assert 0.0 <= event.confidence.value <= 1.0
            assert "score_margin" in event.metadata
        assert result.metadata["confidence_method"] == "score_margin_logistic"
        assert result.metadata["confidence_slope"] == baseline.CONFIDENCE_SLOPE

    def test_the_viterbi_run_does_not_claim_the_threshold_shaped_it(self, tmp_path) -> None:
        wav = write_sine_wav(tmp_path / "tone.wav", seconds=1.0, channels=1)
        result = ENGINE.analyze(wav, ChordAnalysisOptions())

        assert result.metadata["decoder"] == "viterbi"
        assert result.metadata["match_threshold_used"] is False
        assert result.metadata["smoothing_window_used"] is False

    def test_the_majority_decoder_does_use_the_threshold(self, tmp_path) -> None:
        wav = write_sine_wav(tmp_path / "tone.wav", seconds=1.0, channels=1)
        result = ENGINE.analyze(wav, ChordAnalysisOptions(extra={"decoder": "majority"}))

        assert result.metadata["match_threshold_used"] is True
        assert result.metadata["smoothing_window_used"] is True

    def test_time_range_restriction_shifts_the_timeline(self, tmp_path) -> None:
        wav = write_sine_wav(tmp_path / "tone.wav", seconds=4.0, channels=1)
        result = ENGINE.analyze(wav, ChordAnalysisOptions(start=1.0, end=3.0))

        assert result.chords
        assert result.chords[0].start >= 1.0
        assert result.chords[-1].end is not None
        assert result.chords[-1].end <= 3.05
        assert result.metadata["performance"]["audio_seconds"] == pytest.approx(2.0, abs=0.1)

    def test_minimum_duration_merges_short_chords(self, tmp_path) -> None:
        wav = write_sine_wav(tmp_path / "tone.wav", seconds=3.0, channels=1)
        result = ENGINE.analyze(wav, ChordAnalysisOptions(minimum_duration=1.0))

        assert result.chords
        for event in result.chords:
            assert event.end is not None
            assert event.end - event.start >= 1.0 - 1e-9
            assert event.confidence.is_known
