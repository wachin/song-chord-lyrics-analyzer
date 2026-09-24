"""Unit tests for the canonical data model (roadmap section 65)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from song_chord_lyrics_analyzer.models import (
    AnalysisResult,
    AudioDocument,
    BeatEvent,
    ChordEvent,
    ChordQuality,
    ConfidenceLevel,
    ConfidenceScore,
    EngineInfo,
    EngineResult,
    KeyEstimate,
    KeyMode,
    LyricSegment,
    LyricSegmentKind,
    LyricWord,
    NoteEvent,
    Provenance,
    RunStatus,
    Stem,
    StemName,
    TempoEstimate,
    level_for_value,
)


class TestConfidence:
    def test_level_is_derived_from_value(self) -> None:
        assert ConfidenceScore(0.05).level is ConfidenceLevel.VERY_LOW
        assert ConfidenceScore(0.3).level is ConfidenceLevel.LOW
        assert ConfidenceScore(0.5).level is ConfidenceLevel.MEDIUM
        assert ConfidenceScore(0.7).level is ConfidenceLevel.HIGH
        assert ConfidenceScore(0.95).level is ConfidenceLevel.VERY_HIGH

    def test_unknown_is_not_zero(self) -> None:
        score = ConfidenceScore.unknown(source="madmom")
        assert score.value is None
        assert score.level is ConfidenceLevel.UNKNOWN
        assert score.is_known is False
        assert score.source == "madmom"

    def test_from_value_none_is_unknown(self) -> None:
        assert ConfidenceScore.from_value(None).is_known is False
        assert ConfidenceScore.from_value(0.0).value == 0.0

    def test_out_of_range_value_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            ConfidenceScore(1.5)
        with pytest.raises(ValueError):
            level_for_value(-0.1)

    def test_confidence_score_is_hashable(self) -> None:
        assert len({ConfidenceScore(0.5), ConfidenceScore(0.5)}) == 1


class TestChordEvent:
    def test_label_is_rendered_when_missing(self) -> None:
        chord = ChordEvent(start=1.0, end=2.0, root="C", quality=ChordQuality.MAJOR)
        assert chord.label == "C"
        assert chord.duration == pytest.approx(1.0)

    def test_unknown_event_is_not_reported_as_silence(self) -> None:
        assert ChordEvent(start=0.0).label == "?"

    def test_silence_helper(self) -> None:
        silence = ChordEvent.silence(0.0, 4.0, source="baseline")
        assert silence.label == "N"
        assert silence.is_silence is True

    def test_slash_chord_is_rendered(self) -> None:
        chord = ChordEvent(start=0.0, root="C", quality=ChordQuality.MAJOR, bass="E")
        assert chord.to_label() == "C/E"

    def test_bass_equal_to_root_is_not_rendered(self) -> None:
        chord = ChordEvent(start=0.0, root="C", quality=ChordQuality.MAJOR, bass="C")
        assert chord.to_label() == "C"

    def test_invalid_root_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            ChordEvent(start=0.0, root="H")

    def test_end_before_start_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            ChordEvent(start=2.0, end=1.0, root="C")

    def test_negative_start_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            ChordEvent(start=-0.5, root="C")


class TestLyrics:
    def test_word_timestamps_are_optional(self) -> None:
        word = LyricWord(text="hello")
        assert word.has_timestamps is False
        assert word.duration is None

    def test_word_duration(self) -> None:
        word = LyricWord(text="hello", start=1.0, end=1.5)
        assert word.duration == pytest.approx(0.5)

    def test_word_with_reversed_boundaries_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            LyricWord(text="hello", start=1.5, end=1.0)

    def test_segment_reports_missing_word_timestamps(self) -> None:
        segment = LyricSegment(text="hello world", words=[LyricWord(text="hello")])
        assert segment.has_word_timestamps is False
        assert segment.has_timestamps is False

    def test_instrumental_segments_hold_no_fake_words(self) -> None:
        segment = LyricSegment(
            text="[instrumental]", start=0.0, end=8.0, kind=LyricSegmentKind.INSTRUMENTAL
        )
        assert segment.words == []
        assert segment.kind is LyricSegmentKind.INSTRUMENTAL


class TestAudioDocument:
    def test_labels(self) -> None:
        document = AudioDocument(
            path=Path("song.wav"), duration=225.32, channels=2, sample_rate=44100
        )
        assert document.channels_label == "stereo"
        assert document.duration_label == "00:03:45.320"

    def test_channel_labels(self) -> None:
        assert AudioDocument(path="a.wav", channels=1).channels_label == "mono"
        assert AudioDocument(path="a.wav", channels=6).channels_label == "6 channels"
        assert AudioDocument(path="a.wav").channels_label == "unknown"

    def test_bitrate_kbps(self) -> None:
        assert AudioDocument(path="a.wav", bitrate=320_000).bitrate_kbps == pytest.approx(320.0)
        assert AudioDocument(path="a.wav").bitrate_kbps is None

    def test_invalid_values_are_rejected(self) -> None:
        with pytest.raises(ValueError):
            AudioDocument(path="a.wav", channels=0)
        with pytest.raises(ValueError):
            AudioDocument(path="a.wav", sample_rate=-1)
        with pytest.raises(ValueError):
            AudioDocument(path="a.wav", duration=-0.1)

    def test_technical_dict_excludes_tags(self) -> None:
        document = AudioDocument(path="a.mp3", title="A Song", artist="Someone", duration=1.0)
        technical = document.as_technical_dict()
        assert "title" not in technical
        assert "artist" not in technical
        assert technical["duration"] == pytest.approx(1.0)


class TestMusicalModels:
    def test_key_label(self) -> None:
        assert KeyEstimate(tonic="C", mode=KeyMode.MAJOR).label == "C major"
        assert KeyEstimate().label == "unknown"

    def test_invalid_tonic_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            KeyEstimate(tonic="H")

    def test_tempo_keeps_alternatives(self) -> None:
        tempo = TempoEstimate(bpm=90.0, alternatives=[180.0])
        assert tempo.is_ambiguous is True
        assert TempoEstimate(bpm=120.0).is_ambiguous is False

    def test_tempo_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            TempoEstimate(bpm=0)

    def test_beat_position_is_one_based(self) -> None:
        assert BeatEvent(time=0.5, position_in_bar=1).position_in_bar == 1
        with pytest.raises(ValueError):
            BeatEvent(time=0.5, position_in_bar=0)

    def test_note_pitch_range_is_validated(self) -> None:
        with pytest.raises(ValueError):
            NoteEvent(start=0.0, pitch_midi=128)
        assert NoteEvent(start=0.0, pitch_midi=60).pitch_midi == 60

    def test_stem_path_is_coerced(self) -> None:
        stem = Stem(name=StemName.VOCALS, path="vocals.wav")
        assert isinstance(stem.path, Path)


class TestAnalysisContainers:
    def test_engine_result_emptiness(self) -> None:
        empty = EngineResult(engine="baseline", kind="chords")
        assert empty.is_empty is True
        assert (
            EngineResult(
                engine="baseline", kind="chords", chords=[ChordEvent(start=0.0, root="C")]
            ).is_empty
            is False
        )

    def test_analysis_result_defaults(self) -> None:
        result = AnalysisResult(provenance=Provenance(application_version="0.1.0"))
        assert result.has_chords is False
        assert result.has_lyrics is False
        assert result.run.status is RunStatus.PENDING

    def test_run_duration(self) -> None:
        result = AnalysisResult(provenance=Provenance(application_version="0.1.0"))
        result.run.started_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result.run.finished_at = datetime(2026, 1, 1, 12, 0, 5, tzinfo=timezone.utc)
        assert result.run.duration_seconds == pytest.approx(5.0)

    def test_engine_info_is_serializable_metadata(self) -> None:
        info = EngineInfo(name="chroma-baseline", kind="chords", version="0.1.0")
        assert info.kind == "chords"
