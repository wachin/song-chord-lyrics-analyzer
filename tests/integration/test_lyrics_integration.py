"""The lyrics engine over the real pipeline (roadmap Phase E).

The unit tests prove the engine against a canned payload. This file proves the
promise the roadmap makes: a real audio file produces timestamped lyric words
through the same application service and CLI pattern as chords, with the model
recorded as provenance.

Two of these tests drive the *real* engine end to end - real decoding, real
windowing, the real registry, the real command - with only the model replaced by
a stand-in that speaks ``onnx-asr``'s contract, so no download happens in the
suite. The last one runs the real Parakeet weights on the committed vocadito
sample, and is skipped unless those weights are already in the local Hugging
Face cache: tests never download models (``docs/DEVELOPMENT.md`` section 7).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from fixtures.audio import write_chord_wav
from song_chord_lyrics_analyzer.analysis import StepStatus, run_analysis
from song_chord_lyrics_analyzer.cli.main import main
from song_chord_lyrics_analyzer.engines import (
    EngineKind,
    EngineRegistry,
    ParakeetLyricsEngine,
    create_default_registry,
)
from song_chord_lyrics_analyzer.engines import lyrics_parakeet as parakeet
from song_chord_lyrics_analyzer.engines.base import LyricsOptions
from song_chord_lyrics_analyzer.models.analysis import EngineInfo, EngineResult
from song_chord_lyrics_analyzer.models.confidence import ConfidenceScore
from song_chord_lyrics_analyzer.models.lyrics import LyricSegment, LyricWord

pytestmark = pytest.mark.integration

requires_dsp = pytest.mark.skipif(
    importlib.util.find_spec("librosa") is None,
    reason="optional DSP stack (numpy/librosa) not installed",
)
requires_onnx_asr = pytest.mark.skipif(
    importlib.util.find_spec("onnx_asr") is None,
    reason="optional lyrics stack (onnx-asr) not installed",
)

#: Where ``onnx-asr`` keeps the converted Parakeet checkpoint. The presence of
#: the directory is the "already downloaded" signal; nothing here fetches it.
MODEL_CACHE = (
    Path.home() / ".cache" / "huggingface" / "hub" / "models--istupakov--parakeet-tdt-0.6b-v3-onnx"
)
SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "vocadito_6.wav"

DURATION = 25.0


@pytest.fixture
def song(tmp_path: Path) -> Path:
    """A generated 25 s song: one full 20 s window plus a short one."""
    return write_chord_wav(
        tmp_path / "song.wav",
        chords=[(0, 4, 7)],
        seconds_per_chord=DURATION,
    )


class FakeModel:
    """``onnx-asr``'s ``TimestampedResult`` shape, one window at a time."""

    def __init__(self, text: str, tokens: list[str], timestamps: list[float]) -> None:
        self.text = text
        self.tokens = tokens
        self.timestamps = timestamps


class FakeTranscriber:
    """A loaded model stand-in that answers every window the same way."""

    def __init__(self, words: list[tuple[str, float]]) -> None:
        self.words = words
        self.windows: list[int] = []

    def recognize(self, waveform: Any, *, sample_rate: int) -> FakeModel:
        self.windows.append(len(waveform))
        tokens = [f"▁{word}" for word, _ in self.words]
        return FakeModel(
            text=" ".join(word for word, _ in self.words),
            tokens=tokens,
            timestamps=[start for _, start in self.words],
        )


def _patched_engine(monkeypatch: pytest.MonkeyPatch, transcriber: FakeTranscriber) -> None:
    """Make the engine the registry builds use a stand-in model.

    This is the only thing replaced: the decode service, the window planner, the
    reassembly, the engine adapter, the registry, the analysis service and the
    command are all the real ones.
    """
    monkeypatch.setattr(parakeet, "_default_loader", lambda model, quantization: transcriber)
    monkeypatch.setattr(parakeet, "_import_front_end", lambda: importlib.import_module("numpy"))


class TestTheAnalysisServiceStep:
    """The lyrics layer flows through ``run_analysis`` like every other layer."""

    @requires_dsp
    @pytest.mark.skipif(
        ParakeetLyricsEngine().is_available(),
        reason="the optional lyrics stack is installed here; see the skip test below",
    )
    def test_an_uninstalled_engine_is_a_skipped_step_not_an_error(self, song: Path) -> None:
        outcome = run_analysis(song, input_hash=False)

        lyrics_step = next(step for step in outcome.steps if step.kind == "lyrics")
        assert lyrics_step.status is StepStatus.SKIPPED
        assert lyrics_step.engine == "parakeet-onnx"
        assert lyrics_step.detail == "not available"
        assert any("parakeet-onnx" in warning for warning in outcome.result.warnings)
        # ...and the rest of the document is untouched by it.
        assert outcome.result.chords
        assert outcome.result.run.status.value == "partial"
        assert outcome.result.provenance.configuration["lyrics"] == "parakeet-onnx"

    @requires_dsp
    def test_a_registered_lyrics_engine_fills_the_document(self, song: Path) -> None:
        document = run_analysis(song, registry=_registry_with_fake(), input_hash=False).result

        assert [segment.text for segment in document.lyrics] == ["la la la"]
        assert document.provenance.configuration["lyrics"] == "fake-lyrics"
        assert document.run.status.value in {"succeeded", "partial"}

    @requires_dsp
    def test_a_failing_lyrics_engine_never_destroys_the_document(self, song: Path) -> None:
        outcome = run_analysis(song, registry=_registry_with_fake(fail=True), input_hash=False)

        lyrics_step = next(step for step in outcome.steps if step.kind == "lyrics")
        assert lyrics_step.status is StepStatus.FAILED
        assert any("lyrics" in warning for warning in outcome.result.warnings)
        assert outcome.result.chords, "the chord layer must survive a lyrics failure"

    @requires_dsp
    def test_the_layer_can_be_overridden_by_name_like_any_other(self, song: Path) -> None:
        document = run_analysis(
            song,
            registry=_registry_with_fake(),
            engines={"lyrics": "fake-lyrics"},
            input_hash=False,
        ).result

        assert document.lyrics


class TestTheRealEngineOnRealAudio:
    """Decoding, windowing and reassembly executed for real."""

    @requires_dsp
    def test_the_command_windows_a_real_song_and_prints_absolute_timestamps(
        self, song: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        transcriber = FakeTranscriber([("hola", 1.0), ("mundo", 2.5)])
        _patched_engine(monkeypatch, transcriber)

        assert main(["lyrics", str(song)]) == 0

        out = capsys.readouterr().out
        assert "Lyrics" in out
        assert "Engine:   parakeet-onnx" in out
        assert "Windows:  2, 2 with text" in out
        assert "Segments: 2" in out
        # The first window's words are on the song's clock...
        assert "00:00:01.000 00:00:02.500  hola" in out
        # ...and the second window's are offset by the 20 s it started at.
        assert "00:00:21.000 00:00:22.500  hola" in out
        assert [round(count / 16_000) for count in transcriber.windows] == [20, 5]

    @requires_dsp
    def test_the_command_reports_a_missing_stack_instead_of_a_traceback(
        self, song: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def missing() -> Any:
            raise ImportError("No module named 'onnx_asr'")

        # Only availability changes: the registry, the engine it hands out and
        # the command are the real ones.
        monkeypatch.setattr(parakeet, "_import_front_end", missing)

        assert main(["lyrics", str(song)]) == 3

        captured = capsys.readouterr()
        assert "not available" in captured.err
        assert "Traceback" not in captured.err


@requires_onnx_asr
@requires_dsp
@pytest.mark.slow
@pytest.mark.skipif(
    not MODEL_CACHE.exists(),
    reason="Parakeet weights are not in the local cache (tests never download models)",
)
class TestTheRealParakeetWeights:
    """The last mile: this engine against real weights and a real singer.

    Structural honesty only - non-empty transcript, word timestamps inside the
    audio, no invented confidence. The accuracy of these weights on the vocadito
    excerpts is the recorded investigation in ``docs/ENGINE_COMPARISON.md``; this
    test does not re-measure it and claims no WER.
    """

    def test_real_weights_transcribe_the_committed_sample(self) -> None:
        assert SAMPLE.exists(), "the vocadito sample is committed for exactly this"

        result = ParakeetLyricsEngine().transcribe(SAMPLE, LyricsOptions())

        assert result.engine == "parakeet-onnx"
        assert result.lyrics, "real weights on real singing must produce text"
        assert result.metadata["windows_with_text"] >= 1
        for segment in result.lyrics:
            assert segment.source == "parakeet-onnx"
            assert segment.confidence.is_known is False
            assert segment.start is not None and segment.end is not None
            assert 0.0 <= float(segment.start) < float(segment.end)
            for word in segment.words:
                assert word.text
                assert word.confidence.is_known is False
                if word.start is not None:
                    assert word.start < float(segment.end) + 1.0


class _FakeLyricsEngine:
    """A registered lyrics engine that fills the document (or fails on purpose)."""

    name = "fake-lyrics"
    kind = EngineKind.LYRICS

    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    def is_available(self) -> bool:
        return True

    def engine_info(self) -> EngineInfo:
        return EngineInfo(name=self.name, kind=self.kind.value, version="0.0.0")

    def transcribe(self, audio_path: Path, options: Any) -> EngineResult:
        if self._fail:
            raise RuntimeError("the model exploded")
        words = [
            LyricWord(text="la", start=0.0, end=1.0, source=self.name),
            LyricWord(text="la", start=1.0, end=2.0, source=self.name),
            LyricWord(text="la", start=2.0, source=self.name),
        ]
        return EngineResult(
            engine=self.name,
            kind=self.kind.value,
            audio_path=audio_path,
            lyrics=[
                LyricSegment(
                    text="la la la",
                    start=0.0,
                    end=20.0,
                    words=words,
                    confidence=ConfidenceScore.unknown(self.name),
                    source=self.name,
                )
            ],
            processing_time_seconds=0.1,
        )


def _registry_with_fake(*, fail: bool = False) -> EngineRegistry:
    registry = create_default_registry()
    registry.register(_FakeLyricsEngine(fail=fail))
    return registry
