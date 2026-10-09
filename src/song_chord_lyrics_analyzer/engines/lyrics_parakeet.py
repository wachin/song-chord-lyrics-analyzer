"""Parakeet lyrics engine through ``onnx-asr`` (roadmap sections 25 and 26).

The first lyrics engine, and the one the section 25/26 investigation measured
best on this hardware: NVIDIA Parakeet TDT 0.6B v3 exported to ONNX, run by
``onnx-asr`` + ``onnxruntime`` with int8 weights. On the vocadito comparison it
beat faster-whisper ``small`` (WER 0.3722 vs 0.3799, CER 0.1857 vs 0.2725) at
4.7 times the speed (real-time factor 0.20 vs 0.95) and similar peak memory, and
on English - which is where it wins outright - WER 0.08 against 0.23. Those are
the recorded numbers; this module claims no new ones.

Three findings from that research shape the code:

* **Long audio needs our own windows.** ``recognize()`` on a 272 s song returned
  8 garbled words, and the upstream ``with_vad(silero)`` route returned
  *nothing*: a speech VAD does not treat singing as speech. The engine therefore
  always chunks (:mod:`song_chord_lyrics_analyzer.engines.lyrics_chunking`).
* **Demucs stems do not help by default.** On a real production the raw mix won
  or tied for both engines, and the synthetic result did not transfer. The
  engine takes the mix and nothing else.
* **Word timestamps come from token timestamps**, which are what the model
  actually reports. A word's end is the next word's start; the last word of a
  window keeps ``end=None`` because the audio continues and inventing a
  boundary there would be fabrication.

Everything heavy is optional and stays that way: ``is_available()`` reports
whether ``onnx-asr``, ``onnxruntime`` and numpy are importable, the model is
downloaded by ``onnx-asr`` itself into the Hugging Face cache - never into this
repository - and the core package keeps ``dependencies = []``. The transcriber
is injectable, so the pipeline is tested end to end without a download.
"""

from __future__ import annotations

import importlib
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from song_chord_lyrics_analyzer.audio.decode import decode_audio
from song_chord_lyrics_analyzer.engines.base import EngineKind, LyricsOptions
from song_chord_lyrics_analyzer.engines.lyrics_chunking import (
    DEFAULT_CHUNK_SECONDS,
    Chunk,
    offset_segments,
    plan_chunks,
    reassemble,
)
from song_chord_lyrics_analyzer.models.analysis import EngineInfo, EngineResult
from song_chord_lyrics_analyzer.models.confidence import ConfidenceScore
from song_chord_lyrics_analyzer.models.lyrics import (
    LyricSegment,
    LyricSegmentKind,
    LyricWord,
)
from song_chord_lyrics_analyzer.performance import PerformanceProbe
from song_chord_lyrics_analyzer.utils.errors import (
    AudioFileNotFoundError,
    DependencyError,
    InputError,
)

__all__ = [
    "DEFAULT_MODEL",
    "DEFAULT_QUANTIZATION",
    "ENGINE_NAME",
    "ENGINE_VERSION",
    "INSTALL_HINT",
    "SAMPLE_RATE",
    "ParakeetLyricsEngine",
    "Transcript",
    "transcript_from",
    "words_from_transcript",
]

#: Stable, CLI-facing engine identifier.
ENGINE_NAME = "parakeet-onnx"
#: Engine version recorded as provenance in every result.
ENGINE_VERSION = "0.1.0"

#: The measured best option: Parakeet TDT 0.6B v3, multilingual, 25 languages.
DEFAULT_MODEL = "nemo-parakeet-tdt-0.6b-v3"
#: Weight quantization the section 25 measurement used.
DEFAULT_QUANTIZATION = "int8"
#: What the model expects; the shared decode service resamples to it.
SAMPLE_RATE = 16_000

#: Install hint used whenever the optional front end is missing.
INSTALL_HINT = (
    'Install the optional lyrics stack: pip install "song-chord-lyrics-analyzer[lyrics]" '
    "(onnx-asr, onnxruntime). The model itself is downloaded on first use by onnx-asr "
    "into its Hugging Face cache - it is never stored in this repository."
)

#: SentencePiece word marker, which ``onnx-asr`` turns into a plain space.
_WORD_MARKER = "\u2581"


class Transcriber(Protocol):
    """What the engine needs from a loaded model.

    ``onnx-asr``'s ``TimestampedResultsAsrAdapter`` already satisfies this; the
    protocol exists so tests can drive the whole chunking pipeline with a
    stand-in that produces the same payload.
    """

    def recognize(self, waveform: Any, *, sample_rate: int) -> Any:
        """Transcribe one window of samples and return its tokens and timestamps."""
        ...


@dataclass(frozen=True)
class Transcript:
    """One window's raw transcription, in the model's own terms.

    Attributes:
        text: The decoded text exactly as the model produced it (not trimmed).
        tokens: Sub-word tokens, in order.
        timestamps: One timestamp in seconds per token, or ``None`` when the
            model reported none.
    """

    text: str
    tokens: tuple[str, ...] = ()
    timestamps: tuple[float, ...] | None = None


def transcript_from(result: Any) -> Transcript:
    """Read a ``TimestampedResult``-shaped payload into a :class:`Transcript`.

    Args:
        result: Any object exposing ``text``, ``tokens`` and ``timestamps``,
            which is what ``onnx-asr`` returns from ``with_timestamps()``. Missing
            attributes are read as "the model did not report this", never guessed.

    Raises:
        InputError: When the token and timestamp lists disagree in length, which
            would silently mis-time every following word.
    """
    text = getattr(result, "text", "") or ""
    tokens = tuple(getattr(result, "tokens", None) or ())
    raw_stamps = getattr(result, "timestamps", None)
    timestamps: tuple[float, ...] | None = None
    if raw_stamps is not None:
        timestamps = tuple(float(stamp) for stamp in raw_stamps)
        if len(timestamps) != len(tokens):
            raise InputError(
                f"the model reported {len(timestamps)} timestamps for {len(tokens)} tokens",
                hint="Refusing to guess which token each timestamp belongs to.",
            )
    return Transcript(text=str(text), tokens=tokens, timestamps=timestamps)


def _is_word_start(token: str) -> bool:
    """Whether a token begins a new word (the SentencePiece marker)."""
    return token.startswith(" ") or token.startswith(_WORD_MARKER)


def _is_punctuation(text: str) -> bool:
    """Whether a token carries no letters or digits of its own."""
    return bool(text) and not any(character.isalnum() for character in text)


def words_from_transcript(
    transcript: Transcript,
    *,
    source: str = ENGINE_NAME,
) -> list[LyricWord]:
    """Turn one window's tokens into timed words.

    A token that starts with the word marker opens a new word and a token
    without one continues it, which is how the SentencePiece vocabulary encodes
    ``"Hello world"`` as ``["▁Hell", "o", "▁world"]``. Punctuation that arrives
    as its own token is attached to the word before it instead of becoming a
    one-character word.

    Word boundaries are the model's own token timestamps: a word ends where the
    next one starts, and the **last** word of a window keeps ``end=None``,
    because the audio carries on past it and no boundary was reported.

    Confidence is always :meth:`ConfidenceScore.unknown`: ``onnx-asr`` returns
    no calibrated per-word confidence, and this project does not invent one.
    """
    if transcript.timestamps is not None and len(transcript.timestamps) != len(transcript.tokens):
        raise InputError(
            f"got {len(transcript.timestamps)} timestamps for {len(transcript.tokens)} tokens"
        )
    stamps: Sequence[float | None]
    if transcript.timestamps is None:
        stamps = [None] * len(transcript.tokens)
    else:
        stamps = transcript.timestamps

    pending: list[tuple[str, float | None]] = []
    for token, stamp in zip(transcript.tokens, stamps, strict=True):
        text = token.replace(_WORD_MARKER, " ")
        stripped = text.strip()
        if not stripped:
            continue
        if pending and (not _is_word_start(text) or _is_punctuation(stripped)):
            word, start = pending[-1]
            pending[-1] = (word + stripped, start)
            continue
        pending.append((stripped, stamp))

    words: list[LyricWord] = []
    for index, (text, start) in enumerate(pending):
        end = pending[index + 1][1] if index + 1 < len(pending) else None
        if start is not None and end is not None and end < start:
            end = None  # a model that reports out-of-order stamps keeps them honest
        words.append(
            LyricWord(
                text=text,
                start=start,
                end=end,
                confidence=ConfidenceScore.unknown(source),
                source=source,
            )
        )
    return words


def _extra_seconds(options: LyricsOptions, key: str, default: float) -> float:
    """Read one numeric override from ``options.extra``, or the engine default."""
    value = options.extra.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{key} must be a number of seconds, got {value!r}")
    return float(value)


class ParakeetLyricsEngine:
    """Timestamped lyrics with Parakeet TDT 0.6B v3 (int8) through ``onnx-asr``."""

    name = ENGINE_NAME
    kind = EngineKind.LYRICS

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        quantization: str | None = DEFAULT_QUANTIZATION,
        chunk_seconds: float = DEFAULT_CHUNK_SECONDS,
        overlap_seconds: float = 0.0,
        loader: Callable[[str, str | None], Any] | None = None,
    ) -> None:
        """Configure the adapter.

        Args:
            model: Model name or Hugging Face repository ``onnx-asr`` loads.
            quantization: Weight quantization, ``None`` for the model's default.
            chunk_seconds: Window length; the measured default is 20 s.
            overlap_seconds: How much neighbouring windows share (default: none).
            loader: How to turn ``(model, quantization)`` into a
                :class:`Transcriber`. Defaults to ``onnx-asr``'s own loader;
                tests inject a stand-in so the pipeline runs without a download.
        """
        self._model_name = model
        self._quantization = quantization
        self._chunk_seconds = float(chunk_seconds)
        self._overlap_seconds = float(overlap_seconds)
        self._loader = loader if loader is not None else _default_loader
        self._transcriber: Any | None = None

    def is_available(self) -> bool:
        """Whether ``onnx-asr``, ``onnxruntime`` and numpy are importable.

        The model weights are *not* checked here: availability must not depend on
        a download, and the first transcribe call reports a missing model.
        """
        try:
            _import_front_end()
        except ImportError:
            return False
        return True

    def engine_info(self) -> EngineInfo:
        """Identity, licence and capability metadata recorded as provenance."""
        return EngineInfo(
            name=self.name,
            kind=self.kind.value,
            version=ENGINE_VERSION,
            available=self.is_available(),
            description=(
                f"Parakeet TDT 0.6B v3 ({self._quantization or 'default'} ONNX) through "
                f"onnx-asr, transcribed in {self._chunk_seconds:g} s windows."
            ),
            license="MIT (onnx-asr, onnxruntime); model weights CC-BY-4.0",
            model=self._model_name,
            model_version=self._quantization,
            capabilities={
                "device": "cpu",
                "chunk_seconds": self._chunk_seconds,
                "overlap_seconds": self._overlap_seconds,
                "chunks_long_audio": True,
                "word_timestamps": True,
                "confidence": False,
                "downloads_model": True,
            },
        )

    def _transcribe_window(self, samples: Any) -> Transcript:
        """Run one window through the loaded model."""
        if self._transcriber is None:
            self._transcriber = self._loader(self._model_name, self._quantization)
        return transcript_from(self._transcriber.recognize(samples, sample_rate=SAMPLE_RATE))

    def transcribe(self, audio_path: Path, options: LyricsOptions) -> EngineResult:
        """Transcribe ``audio_path`` into timestamped lyric segments.

        Raises:
            AudioFileNotFoundError: When the file does not exist.
            DependencyError: When the optional lyrics stack is not installed.
            InputError: When the file holds no audio, the window options are
                impossible, or the time range is inverted.
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise AudioFileNotFoundError(audio_path)

        startup_started = time.perf_counter()
        try:
            numpy = _import_front_end()
        except ImportError as error:
            raise DependencyError(
                f"Engine {self.name!r} needs onnx-asr, onnxruntime and numpy, "
                "which are not installed.",
                hint=INSTALL_HINT,
            ) from error
        startup_seconds = time.perf_counter() - startup_started

        chunk_seconds = _extra_seconds(options, "chunk_seconds", self._chunk_seconds)
        overlap_seconds = _extra_seconds(options, "overlap_seconds", self._overlap_seconds)
        range_start = 0.0 if options.start is None else float(options.start)
        range_end = options.end
        if range_start < 0.0:
            raise InputError(f"start must not be negative, got {range_start!r}")
        if range_end is not None and range_end <= range_start:
            raise InputError(f"end ({range_end!r}) must be greater than start ({range_start!r})")
        span = None if range_end is None else range_end - range_start

        probe = PerformanceProbe(startup_time_seconds=startup_seconds, device="cpu")
        probe.start()
        try:
            decoded = decode_audio(
                audio_path,
                sample_rate=SAMPLE_RATE,
                mono=True,
                offset=range_start,
                duration=span,
            )
            audio_seconds = decoded.duration
            if audio_seconds <= 0.0:
                raise InputError(
                    f"Engine {self.name!r} decoded no audio from {audio_path.name!r}.",
                    hint="Check that the file contains a decodable audio stream.",
                )
            probe.audio_seconds = audio_seconds

            chunks = plan_chunks(
                audio_seconds,
                chunk_seconds=chunk_seconds,
                overlap_seconds=overlap_seconds,
            )
            waveform = numpy.asarray(decoded.samples, dtype=numpy.float32)
            windows: list[list[LyricSegment]] = []
            silent_windows = 0
            for chunk in chunks:
                segment = self._segment_for(chunk, waveform, options)
                if segment is None:
                    silent_windows += 1
                    windows.append([])
                    continue
                windows.append([segment])
        finally:
            report = probe.stop()

        lyrics = list(reassemble(windows, chunks))
        if range_start:
            # The windows were planned over the requested range, so their
            # timestamps are relative to it: move them onto the file's clock.
            lyrics = offset_segments(lyrics, range_start)
        words = sum(len(segment.words) for segment in lyrics)

        warnings: list[str] = []
        if silent_windows:
            warnings.append(
                f"{silent_windows} of {len(chunks)} windows produced no text; "
                "they are omitted rather than reported as instrumental."
            )

        return EngineResult(
            engine=self.name,
            kind=self.kind.value,
            engine_version=ENGINE_VERSION,
            audio_path=audio_path,
            lyrics=lyrics,
            processing_time_seconds=report.processing_time_seconds,
            warnings=warnings,
            metadata={
                "performance": report.as_dict(),
                "model": self._model_name,
                "quantization": self._quantization,
                "sample_rate": SAMPLE_RATE,
                "chunk_seconds": chunk_seconds,
                "overlap_seconds": overlap_seconds,
                "windows": len(chunks),
                "windows_with_text": len(chunks) - silent_windows,
                "segments": len(lyrics),
                "words": words,
                "range_start": range_start,
                "range_end": range_end,
                "confidence": "unknown (the model reports no calibrated confidence)",
            },
        )

    def _segment_for(
        self,
        chunk: Chunk,
        waveform: Any,
        options: LyricsOptions,
    ) -> LyricSegment | None:
        """Transcribe one window, or return ``None`` when it produced no text."""
        start_frame = round(chunk.start * SAMPLE_RATE)
        end_frame = round(chunk.end * SAMPLE_RATE)
        transcript = self._transcribe_window(waveform[start_frame:end_frame])

        text = transcript.text.strip()
        words = words_from_transcript(transcript, source=self.name)
        if not options.word_timestamps:
            words = []
        if not text and not words:
            return None
        return LyricSegment(
            text=text or " ".join(word.text for word in words),
            # Window-local coordinates: ``reassemble`` is what puts each
            # segment on the song's clock. Offsetting here too would double it.
            # The segment spans the window it was transcribed from (0 .. window
            # length); a line's real end is not invented from token timestamps.
            start=0.0,
            end=chunk.duration,
            words=words,
            confidence=ConfidenceScore.unknown(self.name),
            language=options.language,
            source=self.name,
            kind=LyricSegmentKind.LYRICS,
        )


def _import_front_end() -> Any:
    """Import the optional lyrics stack and return numpy, or raise ``ImportError``."""
    importlib.import_module("onnx_asr")
    importlib.import_module("onnxruntime")
    return importlib.import_module("numpy")


def _default_loader(model: str, quantization: str | None) -> Any:
    """Load ``model`` through ``onnx-asr`` and ask it for token timestamps."""
    onnx_asr = importlib.import_module("onnx_asr")
    loaded = onnx_asr.load_model(model, quantization=quantization)
    return loaded.with_timestamps()
