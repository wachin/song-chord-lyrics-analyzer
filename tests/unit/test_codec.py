"""Unit tests for the canonical JSON codec (roadmap sections 48 and 65)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from song_chord_lyrics_analyzer.models import (
    AlignmentResult,
    AnalysisResult,
    AudioDocument,
    ChordEvent,
    ChordQuality,
    ConfidenceScore,
    EngineInfo,
    KeyEstimate,
    KeyMode,
    LyricSegment,
    LyricWord,
    NoteEvent,
    Provenance,
    RunStatus,
    Stem,
    StemName,
    TempoEstimate,
)
from song_chord_lyrics_analyzer.schema import (
    SCHEMA_VERSION,
    decode,
    encode,
    from_json,
    to_json,
)
from song_chord_lyrics_analyzer.utils.errors import SchemaError


def _sample_result() -> AnalysisResult:
    provenance = Provenance(
        application_version="0.1.0",
        input_path="/music/song.mp3",
        input_hash="deadbeef",
        python_version="3.13.5",
        platform="Linux",
        created_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        engines={"baseline": EngineInfo(name="baseline", kind="chords", version="0.1.0")},
        configuration={"engine": "baseline"},
        preprocessing=["decode"],
        normalization=["merge-identical-chords"],
    )
    result = AnalysisResult(
        provenance=provenance,
        audio=AudioDocument(path=Path("/music/song.mp3"), duration=225.32, sample_rate=44100),
        chords=[
            ChordEvent(
                start=0.0,
                end=2.5,
                root="C",
                quality=ChordQuality.MAJOR,
                label="C",
                confidence=ConfidenceScore(0.84, source="baseline"),
                source="baseline",
                metadata={"template_score": 0.9},
            ),
            ChordEvent.silence(2.5, 3.0),
        ],
        lyrics=[
            LyricSegment(
                text="hello world",
                start=1.0,
                end=2.0,
                words=[LyricWord(text="hello", start=1.0, end=1.4)],
                confidence=ConfidenceScore.unknown(source="whisper"),
            )
        ],
        notes=[NoteEvent(start=0.0, end=0.5, pitch_midi=60, instrument="guitar")],
        stems=[Stem(name=StemName.VOCALS, path=Path("/tmp/vocals.wav"))],
        key=KeyEstimate(tonic="C", mode=KeyMode.MAJOR, confidence=ConfidenceScore(0.87)),
        tempo=TempoEstimate(bpm=92.0, alternatives=[184.0], meter="4/4"),
        engines={"baseline": EngineInfo(name="baseline", kind="chords", version="0.1.0")},
        raw={"baseline": {"labels": ["C", "N"]}},
        warnings=["low confidence on the second chord"],
    )
    result.alignment = AlignmentResult(
        chords=list(result.chords), lyrics=list(result.lyrics), method="beat-snap"
    )
    result.run.status = RunStatus.SUCCEEDED
    return result


class TestEncode:
    def test_primitives_are_unchanged(self) -> None:
        assert encode(None) is None
        assert encode("C") == "C"
        assert encode(3) == 3
        assert encode(1.5) == 1.5
        assert encode(True) is True

    def test_enums_become_their_values(self) -> None:
        assert encode(ChordQuality.MAJOR7) == "maj7"
        assert encode(RunStatus.SUCCEEDED) == "succeeded"

    def test_paths_and_datetimes_become_strings(self) -> None:
        assert encode(Path("/tmp/a.wav")) == "/tmp/a.wav"
        assert encode(datetime(2026, 1, 1, tzinfo=timezone.utc)) == "2026-01-01T00:00:00+00:00"

    def test_unsupported_values_are_rejected(self) -> None:
        with pytest.raises(SchemaError):
            encode(object())


class TestRoundTrip:
    def test_chord_event_round_trip(self) -> None:
        chord = ChordEvent(
            start=0.0,
            end=1.0,
            root="C",
            quality=ChordQuality.MAJOR7,
            bass="E",
            extensions=["9"],
            label="Cmaj7/E",
            confidence=ConfidenceScore(0.5),
            metadata={"evidence": [0.5, 0.1]},
        )
        assert decode(ChordEvent, encode(chord)) == chord

    def test_analysis_result_round_trip(self) -> None:
        result = _sample_result()
        restored = decode(AnalysisResult, encode(result))
        assert restored == result

    def test_json_envelope_round_trip(self) -> None:
        result = _sample_result()
        text = to_json(result)
        assert SCHEMA_VERSION in text
        assert from_json(AnalysisResult, text) == result

    def test_enum_and_path_types_are_restored(self) -> None:
        restored = decode(AnalysisResult, encode(_sample_result()))
        assert isinstance(restored.chords[0].quality, ChordQuality)
        assert isinstance(restored.audio.path, Path)  # type: ignore[union-attr]
        assert restored.run.status is RunStatus.SUCCEEDED
        assert restored.provenance.created_at.tzinfo is not None


class TestDecodeErrors:
    def test_unknown_fields_are_ignored(self) -> None:
        payload = encode(ChordEvent(start=0.0, root="C"))
        payload["future_field"] = "ignored"
        assert decode(ChordEvent, payload).root == "C"

    def test_missing_required_field_is_reported(self) -> None:
        with pytest.raises(SchemaError, match="start"):
            decode(ChordEvent, {"root": "C"})

    def test_unknown_enum_value_is_reported(self) -> None:
        with pytest.raises(SchemaError, match="ChordQuality"):
            decode(ChordEvent, {"start": 0.0, "quality": "definitely-not-a-quality"})

    def test_wrong_json_shape_is_reported(self) -> None:
        with pytest.raises(SchemaError):
            decode(ChordEvent, ["not", "an", "object"])

    def test_invalid_json_is_reported(self) -> None:
        with pytest.raises(SchemaError, match="Invalid JSON"):
            from_json(AnalysisResult, "{not json")

    def test_payload_without_document_is_reported(self) -> None:
        with pytest.raises(SchemaError, match="document"):
            from_json(AnalysisResult, '{"schema_version": "1"}')
