"""Long-song chord analysis (roadmap Phase K): windows, seams and progress.

``analyze_chords_in_windows`` is what makes a long recording analysable without
holding it all in memory, so these tests pin the contract a musician would
notice if it broke: every second of the song is covered exactly once, a chord
split by a window boundary comes back as one chord, an overlapping window does
not duplicate it, and an engine that ignores the time range it was given is
reported instead of producing a duplicated timeline.

The engine here is a stand-in that *honours* the window it is given - the
property the real chroma baseline has (it decodes with ``offset`` and shifts by
it) and that the whole module relies on.
"""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from fixtures.audio import write_sine_wav
from fixtures.fake_key_tempo_engines import FakeKeyEngine, FakeLyricsEngine, FakeTempoEngine
from song_chord_lyrics_analyzer.analysis import (
    ProgressEvent,
    StepStatus,
    analyze_chords_in_windows,
    run_analysis,
)
from song_chord_lyrics_analyzer.analysis.chunking import (
    DEFAULT_CHORD_CHUNK_SECONDS,
    SEAM_TOLERANCE_SECONDS,
)
from song_chord_lyrics_analyzer.cli.main import main
from song_chord_lyrics_analyzer.engines import EngineRegistry
from song_chord_lyrics_analyzer.engines.base import ChordAnalysisOptions, EngineKind
from song_chord_lyrics_analyzer.models.analysis import EngineInfo, EngineResult
from song_chord_lyrics_analyzer.models.confidence import ConfidenceScore
from song_chord_lyrics_analyzer.models.music import ChordEvent
from song_chord_lyrics_analyzer.utils.errors import InputError

#: Length of the fake song: two 6 s windows at the default test window length.
DURATION = 12.0

#: One chord change at 7 s, so a 6 s window boundary lands *inside* the first
#: chord and the seam rules have something real to repair.
SEGMENTS: tuple[tuple[float, float, str], ...] = ((0.0, 7.0, "C"), (7.0, 12.0, "G"))

#: How a chord engine reports its output: absolute ``(start, end, label)`` spans.
Span = tuple[float, float, str]

#: The confidence a fake reports unless a test says otherwise.
UNKNOWN_CONFIDENCE = ConfidenceScore.unknown()


class WindowedChordEngine:
    """A chord engine that honours ``start``/``end`` like the real one.

    It clips its canned spans to the window it was asked for, so a chord that
    crosses a window boundary comes back in two halves - exactly what the seam
    rules exist to repair.
    """

    name = "windowed-chords"
    kind = EngineKind.CHORDS

    def __init__(
        self,
        segments: tuple[Span, ...] = SEGMENTS,
        *,
        duration: float = DURATION,
        processing_time_seconds: float | None = 0.25,
        confidence: ConfidenceScore = UNKNOWN_CONFIDENCE,
        confidences: tuple[ConfidenceScore, ...] | None = None,
        raw: Any | None = None,
        warnings: tuple[str, ...] = (),
        ignore_range: bool = False,
        version: str = "1.0.0",
    ) -> None:
        self.segments = segments
        self.duration = duration
        self.processing_time_seconds = processing_time_seconds
        self.confidence = confidence
        self.confidences = confidences
        self.raw = raw
        self.warnings = warnings
        self.ignore_range = ignore_range
        self.version = version
        self.calls: list[ChordAnalysisOptions] = []

    def is_available(self) -> bool:
        return True

    def engine_info(self) -> EngineInfo:
        return EngineInfo(name=self.name, kind=self.kind.value, version=self.version)

    def analyze(self, audio_path: Path, options: ChordAnalysisOptions) -> EngineResult:
        self.calls.append(options)
        start = 0.0 if self.ignore_range or options.start is None else float(options.start)
        end = self.duration if self.ignore_range or options.end is None else float(options.end)
        events: list[ChordEvent] = []
        for begin, stop, label in self.segments:
            low, high = max(begin, start), min(stop, end)
            if high > low:
                events.append(ChordEvent(start=low, end=high, label=label, source=self.name))
        confidence = self.confidence
        if self.confidences is not None:
            confidence = self.confidences[len(self.calls) - 1]
        return EngineResult(
            engine=self.name,
            kind=self.kind.value,
            engine_version=self.version,
            audio_path=Path(audio_path),
            chords=events,
            confidence=confidence,
            processing_time_seconds=self.processing_time_seconds,
            raw=self.raw,
            warnings=list(self.warnings),
            metadata={
                "performance": {
                    "processing_time_seconds": self.processing_time_seconds,
                    "audio_seconds": end - start,
                }
            },
        )


def _spans(events: list[ChordEvent]) -> list[Span]:
    return [(event.start, event.end, event.label) for event in events]


def _windowed(engine: WindowedChordEngine, **kwargs: Any) -> EngineResult:
    """Run the windowed driver the way the analysis service runs it."""
    duration = kwargs.pop("duration", DURATION)
    chunk_seconds = kwargs.pop("chunk_seconds", 6.0)
    return analyze_chords_in_windows(
        engine,
        Path("song.wav"),
        duration=duration,
        chunk_seconds=chunk_seconds,
        **kwargs,
    )


def _audio(tmp_path: Path) -> Path:
    return write_sine_wav(tmp_path / "song.wav", seconds=DURATION, channels=1)


def _registry(chords: WindowedChordEngine, **layers: Any) -> EngineRegistry:
    """The fake registry, with the window-honouring chord engine first."""
    registry = EngineRegistry()
    registry.register(chords)
    registry.register(layers.get("key", FakeKeyEngine()))
    registry.register(layers.get("tempo", FakeTempoEngine()))
    registry.register(layers.get("lyrics", FakeLyricsEngine()))
    return registry


def _patch_analyze(monkeypatch: pytest.MonkeyPatch, registry: EngineRegistry) -> None:
    """Run ``songlab analyze`` against the fakes, keeping the real service."""
    real = run_analysis

    def _fake(audio_path: Path, **options: Any):
        return real(audio_path, registry=registry, **options)

    monkeypatch.setattr("song_chord_lyrics_analyzer.cli.commands.analyze.run_analysis", _fake)


class TestWindowedChordAnalysis:
    def test_each_window_is_analysed_on_its_own_range(self) -> None:
        engine = WindowedChordEngine()

        _windowed(engine)

        assert [(call.start, call.end) for call in engine.calls] == [(0.0, 6.0), (6.0, 12.0)]

    def test_a_chord_split_by_a_window_boundary_comes_back_as_one_chord(self) -> None:
        merged = _windowed(WindowedChordEngine())

        # C runs 0-7 and is cut at 6 s by the window, G runs 7-12: the seam is
        # repaired, so the musician sees the two chords the song has, not three.
        assert _spans(merged.chords) == [(0.0, 7.0, "C"), (7.0, 12.0, "G")]

    def test_a_same_label_chord_inside_one_window_is_never_joined(self) -> None:
        """Only a seam is repaired; what the engine reported inside a window stays."""
        engine = WindowedChordEngine(segments=((0.0, 2.0, "C"), (3.0, 6.0, "C"), (6.0, 12.0, "G")))

        merged = _windowed(engine)

        # The 1 s gap between the two C's is longer than a frame: two chords.
        # The C/G change at the 6 s seam is untouched by the join rule.
        assert _spans(merged.chords) == [
            (0.0, 2.0, "C"),
            (3.0, 6.0, "C"),
            (6.0, 12.0, "G"),
        ]
        assert SEAM_TOLERANCE_SECONDS < 1.0

    def test_overlapping_windows_do_not_duplicate_a_chord(self) -> None:
        merged = _windowed(WindowedChordEngine(), chunk_seconds=6.0, overlap_seconds=2.0)

        # Windows 0-6, 4-10 and 8-12 all report parts of the same two chords;
        # an earlier window wins and coverage is still complete.
        assert _spans(merged.chords) == [(0.0, 7.0, "C"), (7.0, 12.0, "G")]

    def test_the_coverage_is_continuous_from_zero_to_the_end(self) -> None:
        merged = _windowed(WindowedChordEngine(), chunk_seconds=5.0)

        events = merged.chords
        assert events[0].start == 0.0
        assert events[-1].end == pytest.approx(DURATION)
        for earlier, later in pairwise(events):
            assert earlier.end == later.start  # no gap, no overlap

    def test_the_events_come_back_on_the_files_own_timeline(self) -> None:
        """A window's local time is never reported: window 3 starts at 20 s."""
        engine = WindowedChordEngine(segments=((0.0, 7.0, "C"), (7.0, 30.0, "G")), duration=30.0)

        merged = _windowed(engine, duration=30.0, chunk_seconds=10.0)

        assert [(call.start, call.end) for call in engine.calls] == [
            (0.0, 10.0),
            (10.0, 20.0),
            (20.0, 30.0),
        ]
        # Each window reported its own slice; joined, they cover the file once,
        # so the G cannot have been left at any window's local zero.
        assert _spans(merged.chords) == [(0.0, 7.0, "C"), (7.0, 30.0, "G")]

    def test_a_recording_that_fits_one_window_is_a_single_whole_file_call(self) -> None:
        engine = WindowedChordEngine()

        merged = _windowed(engine, duration=3.0, chunk_seconds=DEFAULT_CHORD_CHUNK_SECONDS)

        assert len(engine.calls) == 1
        assert engine.calls[0].start is None  # one pass, no windowing at all
        assert "windows" not in merged.metadata

    def test_an_unknown_duration_is_a_single_whole_file_call(self) -> None:
        engine = WindowedChordEngine()

        merged = _windowed(engine, duration=None)

        assert len(engine.calls) == 1
        assert engine.calls[0].start is None
        assert "windows" not in merged.metadata

    def test_an_engine_that_ignores_the_range_is_reported_not_concatenated(self) -> None:
        engine = WindowedChordEngine(ignore_range=True)

        with pytest.raises(InputError, match=r"returned an event at 0\.000 s"):
            _windowed(engine)

    def test_the_observer_is_told_each_window(self) -> None:
        seen: list[tuple[int, int, float, float]] = []

        _windowed(
            WindowedChordEngine(),
            on_window=lambda index, total, chunk: seen.append(
                (index, total, chunk.start, chunk.end)
            ),
        )

        assert seen == [(1, 2, 0.0, 6.0), (2, 2, 6.0, 12.0)]

    def test_the_run_cost_is_the_sum_of_the_windows(self) -> None:
        merged = _windowed(WindowedChordEngine(processing_time_seconds=0.25))

        assert merged.processing_time_seconds == pytest.approx(0.5)
        assert merged.metadata["performance"]["processing_time_seconds"] == pytest.approx(0.5)
        assert merged.metadata["performance"]["audio_seconds"] == pytest.approx(DURATION)

    def test_an_unmetered_window_leaves_the_total_unmeasured(self) -> None:
        merged = _windowed(WindowedChordEngine(processing_time_seconds=None))

        assert merged.processing_time_seconds is None  # never a partial sum

    def test_the_merged_result_keeps_the_engines_identity_and_drops_raw(self) -> None:
        merged = _windowed(WindowedChordEngine(raw={"frame_labels": ["C"]}, version="2.1.0"))

        assert merged.engine == "windowed-chords"
        assert merged.engine_version == "2.1.0"
        assert merged.kind == EngineKind.CHORDS.value
        assert merged.metadata["windows"] == 2
        assert merged.metadata["chunk_seconds"] == 6.0
        assert merged.raw is None  # per-window payloads are not one payload

    def test_confidence_survives_only_when_every_window_agrees(self) -> None:
        agreed = ConfidenceScore.from_value(0.8, "windowed-chords")
        split = (
            ConfidenceScore.from_value(0.8, "windowed-chords"),
            ConfidenceScore.from_value(0.4, "windowed-chords"),
        )

        assert _windowed(WindowedChordEngine(confidence=agreed)).confidence == agreed
        assert (
            _windowed(WindowedChordEngine(confidences=split)).confidence
            == ConfidenceScore.unknown()
        )


class TestProgressEvents:
    def test_a_whole_file_step_reports_itself_once(self, tmp_path: Path) -> None:
        seen: list[ProgressEvent] = []

        run_analysis(
            _audio(tmp_path),
            registry=_registry(WindowedChordEngine()),
            on_progress=seen.append,
        )

        assert [(event.kind, event.completed, event.total) for event in seen] == [
            ("chords", 0, 1),
            ("lyrics", 0, 1),
            ("key", 0, 1),
            ("tempo", 0, 1),
        ]
        assert all(event.detail is None for event in seen)
        assert all(event.fraction == 0.0 for event in seen)

    def test_a_windowed_step_reports_every_window(self, tmp_path: Path) -> None:
        seen: list[ProgressEvent] = []

        run_analysis(
            _audio(tmp_path),
            registry=_registry(WindowedChordEngine()),
            chord_chunk_seconds=6.0,
            on_progress=seen.append,
        )

        chords = [event for event in seen if event.kind == "chords"]
        assert [event.detail for event in chords] == [
            None,
            "window 1 of 2",
            "window 2 of 2",
        ]
        assert [event.engine for event in chords] == ["windowed-chords"] * 3
        assert [event.fraction for event in chords] == [0.0, 0.5, 1.0]

    def test_the_event_refuses_impossible_counts(self) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            ProgressEvent("chords", "engine", 0, 0)
        with pytest.raises(ValueError, match="0 <= completed <= total"):
            ProgressEvent("chords", "engine", 3, 2)

    def test_a_failing_reporter_is_not_swallowed(self, tmp_path: Path) -> None:
        """A broken reporter is a bug in the call path, not something to hide."""

        def _explode(_event: ProgressEvent) -> None:
            raise RuntimeError("reporter is broken")

        with pytest.raises(RuntimeError, match="reporter is broken"):
            run_analysis(
                _audio(tmp_path),
                registry=_registry(WindowedChordEngine()),
                on_progress=_explode,
            )


class TestChunkingInTheAnalysisService:
    def test_windowed_chords_land_in_the_document_and_the_provenance(self, tmp_path: Path) -> None:
        engine = WindowedChordEngine()

        outcome = run_analysis(
            _audio(tmp_path),
            registry=_registry(engine),
            chord_chunk_seconds=6.0,
        )

        assert _spans(outcome.result.chords) == [(0.0, 7.0, "C"), (7.0, 12.0, "G")]
        configuration = outcome.result.provenance.configuration
        assert configuration["chords_chunk_seconds"] == "6"
        assert "chords_overlap_seconds" not in configuration
        step = next(step for step in outcome.steps if step.kind == "chords")
        assert step.detail == "2 chords, 2 windows"
        assert step.processing_time_seconds == pytest.approx(0.5)

    def test_the_overlap_is_recorded_when_one_was_asked_for(self, tmp_path: Path) -> None:
        outcome = run_analysis(
            _audio(tmp_path),
            registry=_registry(WindowedChordEngine()),
            chord_chunk_seconds=6.0,
            chord_overlap_seconds=2.0,
        )

        assert outcome.result.provenance.configuration["chords_overlap_seconds"] == "2"

    def test_without_the_option_the_chord_layer_is_one_whole_file_pass(
        self, tmp_path: Path
    ) -> None:
        engine = WindowedChordEngine()

        outcome = run_analysis(_audio(tmp_path), registry=_registry(engine))

        assert len(engine.calls) == 1
        assert engine.calls[0].start is None
        assert "chords_chunk_seconds" not in outcome.result.provenance.configuration
        assert outcome.result.run.status.value == "succeeded"

    def test_only_the_chord_layer_is_windowed(self, tmp_path: Path) -> None:
        """Key and tempo need the whole song; lyrics chunk inside the engine."""
        key, tempo, lyrics = FakeKeyEngine(), FakeTempoEngine(), FakeLyricsEngine()

        run_analysis(
            _audio(tmp_path),
            registry=_registry(WindowedChordEngine(), key=key, tempo=tempo, lyrics=lyrics),
            chord_chunk_seconds=6.0,
        )

        assert len(key.calls) == 1
        assert len(tempo.calls) == 1
        assert len(lyrics.calls) == 1  # the engine, not the service, decides windows

    def test_an_engine_that_ignores_the_range_fails_only_its_step(self, tmp_path: Path) -> None:
        outcome = run_analysis(
            _audio(tmp_path),
            registry=_registry(WindowedChordEngine(ignore_range=True)),
            chord_chunk_seconds=6.0,
        )

        chords = next(step for step in outcome.steps if step.kind == "chords")
        assert chords.status is StepStatus.FAILED
        assert "returned an event" in (chords.detail or "")
        assert outcome.result.chords == []
        assert outcome.result.key is not None  # the other layers still ran
        assert any("returned an event" in warning for warning in outcome.result.warnings)

    @pytest.mark.parametrize(
        ("chunk_seconds", "overlap_seconds", "message"),
        [
            (0.0, 0.0, "window length must be positive"),
            (-1.0, 0.0, "window length must be positive"),
            (6.0, -1.0, "overlap must not be negative"),
            (6.0, 6.0, "overlap must be smaller"),
        ],
    )
    def test_impossible_windowing_options_are_rejected_before_anything_is_read(
        self, tmp_path: Path, chunk_seconds: float, overlap_seconds: float, message: str
    ) -> None:
        engine = WindowedChordEngine()

        # The path does not even exist: an impossible option is reported before
        # the audio is probed, so a typo never costs a decode of a long file.
        with pytest.raises(InputError, match=message):
            run_analysis(
                tmp_path / "absent.wav",
                registry=_registry(engine),
                chord_chunk_seconds=chunk_seconds,
                chord_overlap_seconds=overlap_seconds,
            )

        assert engine.calls == []


class TestTheAnalyzeCommandFlags:
    """The flags a user types: they reach the service and print where promised."""

    def test_the_window_flag_windows_the_chord_layer(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine = WindowedChordEngine()
        _patch_analyze(monkeypatch, _registry(engine))

        assert main(["analyze", str(_audio(tmp_path)), "--chord-chunk-seconds", "6"]) == 0

        assert [(call.start, call.end) for call in engine.calls] == [(0.0, 6.0), (6.0, 12.0)]
        assert "2 chords, 2 windows" in capsys.readouterr().out

    def test_the_overlap_flag_reaches_the_service(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_analyze(monkeypatch, _registry(WindowedChordEngine()))

        assert (
            main(
                [
                    "analyze",
                    str(_audio(tmp_path)),
                    "--chord-chunk-seconds",
                    "6",
                    "--chord-overlap-seconds",
                    "2",
                ]
            )
            == 0
        )

        # Three overlapping windows, still the song's two chords.
        assert "2 chords, 3 windows" in capsys.readouterr().out

    def test_progress_goes_to_stderr_and_never_into_the_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_analyze(monkeypatch, _registry(WindowedChordEngine()))

        assert (
            main(
                [
                    "analyze",
                    str(_audio(tmp_path)),
                    "--json",
                    "--chord-chunk-seconds",
                    "6",
                    "--progress",
                ]
            )
            == 0
        )

        captured = capsys.readouterr()
        document = json.loads(captured.out)  # stdout is still exactly the document
        assert len(document["chords"]) == 2
        assert "chords: window 1 of 2" in captured.err
        assert "chords: window 2 of 2" in captured.err
        assert "key: fake-key" in captured.err
        assert "chords: window 1 of 2" not in captured.out

    def test_an_impossible_window_length_is_an_input_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_analyze(monkeypatch, _registry(WindowedChordEngine()))

        assert main(["analyze", str(_audio(tmp_path)), "--chord-chunk-seconds", "0"]) == 2

        assert "window length must be positive" in capsys.readouterr().err

    def test_an_overlap_without_a_window_length_is_an_input_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_analyze(monkeypatch, _registry(WindowedChordEngine()))

        assert main(["analyze", str(_audio(tmp_path)), "--chord-overlap-seconds", "2"]) == 2

        assert "needs a window length" in capsys.readouterr().err
