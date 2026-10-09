"""The Parakeet lyrics engine (roadmap Phase E, sections 25 and 26).

The engine is tested in two halves. Its model-free half - reading what a model
returned, turning tokens into timed words, loading once per run, reporting
honest metadata and honest dependency errors - is driven by an injected
stand-in that speaks ``onnx-asr``'s own contract, so it runs everywhere. The
decoding and windowing half is executed only where the optional DSP stack is
installed, exactly as :meth:`ParakeetLyricsEngine.is_available` promises.

Nothing here downloads a model: the integration test that runs real weights is
gated on the weights already being in the local cache.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from fixtures.audio import write_sine_wav
from song_chord_lyrics_analyzer.engines import EngineKind
from song_chord_lyrics_analyzer.engines import lyrics_parakeet as parakeet
from song_chord_lyrics_analyzer.engines.base import LyricsOptions
from song_chord_lyrics_analyzer.utils.errors import (
    AudioFileNotFoundError,
    DependencyError,
    InputError,
)

requires_dsp = pytest.mark.skipif(
    importlib.util.find_spec("librosa") is None,
    reason="optional DSP stack (numpy/librosa) not installed",
)


@dataclass
class FakeResult:
    """Shaped like ``onnx_asr.asr.TimestampedResult``, field for field."""

    text: str
    tokens: list[str] | None = None
    timestamps: list[float] | None = None
    logprobs: list[float] | None = None


@dataclass
class FakeTranscriber:
    """A loaded model stand-in: only ``recognize`` is part of the contract."""

    results: list[FakeResult] = field(default_factory=list)
    received_samples: list[int] = field(default_factory=list)
    sample_rates: list[int] = field(default_factory=list)

    def recognize(self, waveform: Any, *, sample_rate: int) -> FakeResult:
        self.received_samples.append(len(waveform))
        self.sample_rates.append(sample_rate)
        index = len(self.received_samples) - 1
        if index < len(self.results):
            return self.results[index]
        return FakeResult("")


def _engine(
    transcriber: FakeTranscriber,
    **kwargs: Any,
) -> tuple[parakeet.ParakeetLyricsEngine, list[tuple[str, str | None]]]:
    """Build an engine whose model loading is recorded instead of performed."""
    loaded: list[tuple[str, str | None]] = []

    def loader(model: str, quantization: str | None) -> FakeTranscriber:
        loaded.append((model, quantization))
        return transcriber

    return parakeet.ParakeetLyricsEngine(loader=loader, **kwargs), loaded


def _transcript(text: str, tokens: list[str], timestamps: list[float]) -> FakeResult:
    return FakeResult(text=text, tokens=tokens, timestamps=timestamps)


def _words(result: parakeet.Transcript) -> list[str]:
    return [word.text for word in parakeet.words_from_transcript(result)]


class TestEngineIdentity:
    def test_it_is_a_lyrics_engine_with_a_stable_name(self) -> None:
        engine = parakeet.ParakeetLyricsEngine()

        assert engine.name == "parakeet-onnx"
        assert engine.kind is EngineKind.LYRICS

    def test_provenance_records_model_licence_and_capabilities(self) -> None:
        info = parakeet.ParakeetLyricsEngine().engine_info()

        assert info.name == "parakeet-onnx"
        assert info.kind == "lyrics"
        assert info.version == parakeet.ENGINE_VERSION
        assert info.model == "nemo-parakeet-tdt-0.6b-v3"
        assert info.license is not None
        assert "MIT" in info.license and "CC-BY-4.0" in info.license
        assert info.capabilities["chunk_seconds"] == 20.0
        assert info.capabilities["chunks_long_audio"] is True
        assert info.capabilities["word_timestamps"] is True
        assert info.capabilities["confidence"] is False
        assert info.capabilities["downloads_model"] is True

    def test_availability_is_false_without_the_optional_stack(self, monkeypatch) -> None:
        def _missing() -> Any:
            raise ImportError("No module named 'onnx_asr'")

        monkeypatch.setattr(parakeet, "_import_front_end", _missing)

        assert parakeet.ParakeetLyricsEngine().is_available() is False

    def test_availability_is_true_when_the_stack_imports(self, monkeypatch) -> None:
        monkeypatch.setattr(parakeet, "_import_front_end", lambda: object())

        assert parakeet.ParakeetLyricsEngine().is_available() is True

    def test_availability_never_downloads_a_model(self, monkeypatch) -> None:
        """A missing model is a transcription-time problem, not an import one."""
        monkeypatch.setattr(parakeet, "_import_front_end", lambda: object())

        assert parakeet.ParakeetLyricsEngine().is_available() is True


class TestTranscriptParsing:
    def test_a_real_shaped_payload_is_read_field_for_field(self) -> None:
        transcript = parakeet.transcript_from(
            FakeResult(text="hello", tokens=["▁hello"], timestamps=[0.25])
        )

        assert transcript.text == "hello"
        assert transcript.tokens == ("▁hello",)
        assert transcript.timestamps == pytest.approx((0.25,))

    def test_missing_fields_are_read_as_not_reported(self) -> None:
        transcript = parakeet.transcript_from(FakeResult(text="hello"))

        assert transcript.tokens == ()
        assert transcript.timestamps is None

    def test_an_empty_payload_is_not_an_error(self) -> None:
        assert parakeet.transcript_from(FakeResult("")) == parakeet.Transcript("")

    def test_a_token_timestamp_mismatch_is_refused(self) -> None:
        with pytest.raises(InputError, match="2 timestamps for 3 tokens"):
            parakeet.transcript_from(
                FakeResult(text="abc", tokens=["a", "b", "c"], timestamps=[0.0, 0.1])
            )

    def test_timestamps_are_coerced_to_floats(self) -> None:
        transcript = parakeet.transcript_from(FakeResult(text="a", tokens=["a"], timestamps=[1]))

        assert transcript.timestamps == (1.0,)


class TestWordsFromTokens:
    def test_the_word_marker_splits_tokens_into_words(self) -> None:
        result = parakeet.transcript_from(
            FakeResult(
                text="Hello world",
                tokens=["▁Hell", "o", "▁world"],
                timestamps=[0.0, 0.1, 0.5],
            )
        )

        assert _words(result) == ["Hello", "world"]

    def test_a_plain_space_marker_words_the_same_way(self) -> None:
        """ ""onnx-asr`` replaces the SentencePiece marker with a space."""
        result = parakeet.transcript_from(
            FakeResult(text="Hello", tokens=[" Hell", "o"], timestamps=[0.0, 0.1])
        )

        assert _words(result) == ["Hello"]

    def test_punctuation_riding_on_a_token_is_not_a_word(self) -> None:
        result = parakeet.transcript_from(
            FakeResult(
                text="Hello world!",
                tokens=["▁Hello", "▁world", "!"],
                timestamps=[0.0, 0.4, 0.9],
            )
        )

        assert _words(result) == ["Hello", "world!"]

    def test_punctuation_that_opens_a_token_joins_the_word_before_it(self) -> None:
        result = parakeet.transcript_from(
            FakeResult(text="Hello,", tokens=["▁Hello", " ,"], timestamps=[0.0, 0.3])
        )

        assert _words(result) == ["Hello,"]

    def test_a_word_ends_where_the_next_one_starts(self) -> None:
        result = parakeet.transcript_from(
            FakeResult(text="one two", tokens=["▁one", "▁two"], timestamps=[0.0, 0.75])
        )

        words = parakeet.words_from_transcript(result)

        assert (words[0].start, words[0].end) == (0.0, 0.75)
        assert words[1].start == 0.75

    def test_the_last_word_keeps_an_unknown_end(self) -> None:
        """The audio carries on past it; no boundary was reported."""
        result = parakeet.transcript_from(
            FakeResult(text="one two", tokens=["▁one", "▁two"], timestamps=[0.0, 0.75])
        )

        words = parakeet.words_from_transcript(result)

        assert words[1].end is None
        assert words[1].has_timestamps is False

    def test_without_timestamps_the_words_have_none(self) -> None:
        result = parakeet.transcript_from(FakeResult(text="one two", tokens=["▁one", "▁two"]))

        words = parakeet.words_from_transcript(result)

        assert _words(result) == ["one", "two"]
        assert all(word.start is None and word.end is None for word in words)
        assert not any(word.has_timestamps for word in words)

    def test_confidence_is_unknown_and_attributed(self) -> None:
        result = parakeet.transcript_from(FakeResult(text="one", tokens=["▁one"], timestamps=[0.0]))

        word = parakeet.words_from_transcript(result)[0]

        assert word.confidence.is_known is False
        assert word.confidence.source == "parakeet-onnx"
        assert word.source == "parakeet-onnx"

    def test_out_of_order_timestamps_do_not_produce_a_negative_duration(self) -> None:
        result = parakeet.transcript_from(
            FakeResult(text="one two", tokens=["▁one", "▁two"], timestamps=[5.0, 1.0])
        )

        words = parakeet.words_from_transcript(result)

        assert words[0].end is None

    def test_whitespace_only_tokens_are_skipped(self) -> None:
        result = parakeet.transcript_from(
            FakeResult(text="one", tokens=["▁one", " "], timestamps=[0.0, 0.5])
        )

        assert _words(result) == ["one"]

    def test_an_empty_transcript_has_no_words(self) -> None:
        assert parakeet.words_from_transcript(parakeet.Transcript("")) == []


@requires_dsp
class TestTranscribeOverWindows:
    """Real decoding, real windowing, a stand-in model on the other end."""

    @pytest.fixture
    def song(self, tmp_path: Path) -> Path:
        """Twenty-five seconds of audio: one full window plus a short one."""
        return write_sine_wav(
            tmp_path / "song.wav",
            seconds=25.0,
            sample_rate=16_000,
            channels=1,
        )

    def test_it_windows_the_song_and_places_the_words_on_the_song_clock(self, song: Path) -> None:
        transcriber = FakeTranscriber(
            results=[
                _transcript("Hello world", ["▁Hello", "▁world"], [1.0, 2.0]),
                _transcript("Farewell", ["▁Farewell"], [0.25]),
            ]
        )
        engine, _ = _engine(transcriber)

        result = engine.transcribe(song, LyricsOptions())

        assert [segment.text for segment in result.lyrics] == ["Hello world", "Farewell"]
        assert result.lyrics[0].words[0].start == pytest.approx(1.0)
        assert result.lyrics[1].start == pytest.approx(20.0)
        assert result.lyrics[1].words[0].start == pytest.approx(20.25)

    def test_every_window_is_a_window_and_the_model_lands_once(self, song: Path) -> None:
        transcriber = FakeTranscriber(results=[_transcript("text", ["▁text"], [0.0])] * 2)
        engine, loaded = _engine(transcriber)

        engine.transcribe(song, LyricsOptions())

        assert len(loaded) == 1
        assert loaded[0] == ("nemo-parakeet-tdt-0.6b-v3", "int8")
        assert transcriber.sample_rates == [16_000, 16_000]
        assert transcriber.received_samples[0] == 20 * 16_000
        assert transcriber.received_samples[1] == pytest.approx(5 * 16_000, abs=2)

    def test_the_model_is_loaded_once_and_reused_across_runs(self, song: Path) -> None:
        transcriber = FakeTranscriber(results=[_transcript("text", ["▁text"], [0.0])] * 4)
        engine, loaded = _engine(transcriber)

        engine.transcribe(song, LyricsOptions())
        engine.transcribe(song, LyricsOptions())

        assert len(loaded) == 1

    def test_the_result_carries_the_run_cost_the_model_and_the_windows(self, song: Path) -> None:
        transcriber = FakeTranscriber(
            results=[_transcript("Hello there", ["▁Hello", "▁there"], [0.0, 1.0])] * 2
        )
        engine, _ = _engine(transcriber)

        result = engine.transcribe(song, LyricsOptions())

        assert result.engine == "parakeet-onnx"
        assert result.kind == "lyrics"
        assert result.audio_path == song
        assert result.processing_time_seconds is not None
        assert result.metadata["performance"]["audio_seconds"] == pytest.approx(25.0)
        assert result.metadata["windows"] == 2
        assert result.metadata["windows_with_text"] == 2
        assert result.metadata["segments"] == 2
        assert result.metadata["words"] == 4
        assert result.metadata["model"] == "nemo-parakeet-tdt-0.6b-v3"

    def test_a_window_without_text_is_omitted_and_reported(self, song: Path) -> None:
        transcriber = FakeTranscriber(results=[_transcript("", [], []), _transcript("", [], [])])
        engine, _ = _engine(transcriber)

        result = engine.transcribe(song, LyricsOptions())

        assert result.lyrics == []
        assert result.metadata["windows_with_text"] == 0
        assert any("2 of 2 windows produced no text" in warning for warning in result.warnings)

    def test_the_window_length_can_be_overridden_per_run(self, song: Path) -> None:
        transcriber = FakeTranscriber(results=[_transcript("t", ["▁t"], [0.0])] * 4)
        engine, _ = _engine(transcriber)

        result = engine.transcribe(song, LyricsOptions(extra={"chunk_seconds": 10.0}))

        assert result.metadata["windows"] == 3
        assert transcriber.received_samples[:2] == [10 * 16_000, 10 * 16_000]

    def test_an_overlap_can_be_asked_for(self, song: Path) -> None:
        transcriber = FakeTranscriber(results=[_transcript("t", ["▁t"], [0.0])] * 4)
        engine, _ = _engine(transcriber)

        result = engine.transcribe(
            song,
            LyricsOptions(extra={"chunk_seconds": 10.0, "overlap_seconds": 2.0}),
        )

        assert result.metadata["overlap_seconds"] == 2.0
        assert result.metadata["windows"] == 3

    def test_a_non_numeric_window_override_is_refused(self, song: Path) -> None:
        engine, _ = _engine(FakeTranscriber())

        with pytest.raises(InputError, match="chunk_seconds must be a number"):
            engine.transcribe(song, LyricsOptions(extra={"chunk_seconds": "10"}))

    def test_word_timestamps_can_be_turned_off(self, song: Path) -> None:
        transcriber = FakeTranscriber(
            results=[_transcript("Hello world", ["▁Hello", "▁world"], [0.0, 1.0])] * 2
        )
        engine, _ = _engine(transcriber)

        result = engine.transcribe(song, LyricsOptions(word_timestamps=False))

        assert result.lyrics[0].text == "Hello world"
        assert result.lyrics[0].words == []
        assert result.metadata["words"] == 0

    def test_a_time_range_is_transcribed_and_offset_onto_the_song_clock(self, song: Path) -> None:
        transcriber = FakeTranscriber(results=[_transcript("middle", ["▁middle"], [0.5])])
        engine, _ = _engine(transcriber)

        result = engine.transcribe(song, LyricsOptions(start=5.0, end=15.0))

        assert transcriber.received_samples[0] == pytest.approx(10 * 16_000, abs=3)
        assert result.lyrics[0].start == pytest.approx(5.0)
        assert result.lyrics[0].words[0].start == pytest.approx(5.5)

    def test_a_negative_start_is_refused(self, song: Path) -> None:
        engine, _ = _engine(FakeTranscriber())

        with pytest.raises(InputError, match="start must not be negative"):
            engine.transcribe(song, LyricsOptions(start=-1.0))

    def test_an_inverted_range_is_refused(self, song: Path) -> None:
        engine, _ = _engine(FakeTranscriber())

        with pytest.raises(InputError, match="must be greater than start"):
            engine.transcribe(song, LyricsOptions(start=10.0, end=5.0))

    def test_a_missing_file_is_an_audio_error(self, tmp_path: Path) -> None:
        engine, _ = _engine(FakeTranscriber())

        with pytest.raises(AudioFileNotFoundError):
            engine.transcribe(tmp_path / "nope.wav", LyricsOptions())

    def test_a_missing_model_stack_is_a_dependency_error_with_an_install_hint(
        self, song: Path, monkeypatch
    ) -> None:
        def _missing() -> Any:
            raise ImportError("No module named 'onnxruntime'")

        monkeypatch.setattr(parakeet, "_import_front_end", _missing)
        engine, _ = _engine(FakeTranscriber())

        with pytest.raises(DependencyError, match="onnx-asr, onnxruntime and numpy") as excinfo:
            engine.transcribe(song, LyricsOptions())

        assert "song-chord-lyrics-analyzer[lyrics]" in (excinfo.value.hint or "")

    def test_a_loader_that_cannot_get_the_model_fails_honestly(self, song: Path) -> None:
        def loader(model: str, quantization: str | None) -> Any:
            raise DependencyError(
                "could not download the Parakeet weights",
                hint="Run with network access, or point the cache at a local copy.",
            )

        engine = parakeet.ParakeetLyricsEngine(loader=loader)

        with pytest.raises(DependencyError, match="could not download"):
            engine.transcribe(song, LyricsOptions())
