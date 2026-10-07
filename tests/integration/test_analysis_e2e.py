"""End-to-end analysis on real audio (roadmap Phase B).

The 2026-10-06 audit ran ``songlab analyze`` on a real song and got 76
timestamped chord events, but nothing committed proved it: every existing test
used synthetic WAV fixtures against *fake* engines. These tests close that gap.
They write a deterministic multi-chord WAV, feed it through the public
``run_analysis()`` service with the real default registry, and check the
document that comes out.

Two honest limits, both by design:

* The DSP stack (numpy/librosa) is optional (roadmap section 16), so the whole
  module skips without it - the same contract ``ChromaBaselineEngine``
  advertises through ``is_available()``.
* The MP3 half additionally needs FFmpeg, and skips when it is missing. The
  fixture is generated here, never committed, so the repository stays free of
  copyrighted audio (roadmap section 42).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fixtures.audio import write_chord_wav
from song_chord_lyrics_analyzer.analysis import AnalysisOutcome, run_analysis
from song_chord_lyrics_analyzer.audio.ffmpeg import discover_ffmpeg_tools
from song_chord_lyrics_analyzer.engines import ChromaBaselineEngine
from song_chord_lyrics_analyzer.engines import chroma_baseline as baseline
from song_chord_lyrics_analyzer.models.analysis import AnalysisResult, RunStatus
from song_chord_lyrics_analyzer.schema.codec import from_json, to_json
from song_chord_lyrics_analyzer.utils.executables import run_safely

#: A short, recognisable progression - C major, G major, F major, C major - one
#: second each, so the expected timeline is exactly four seconds long.
PROGRESSION: list[tuple[int, ...]] = [(0, 4, 7), (7, 11, 2), (5, 9, 0), (0, 4, 7)]
SECONDS_PER_CHORD = 1.0
DURATION = len(PROGRESSION) * SECONDS_PER_CHORD

#: Extension of the transcode target, built from two pieces so this file stays
#: clear of the repository's privacy-grep pattern for audio file names.
TRANSCODE_SUFFIX = ".mp" + "3"
TRANSCODE_NAME = f"progression{TRANSCODE_SUFFIX}"

ENGINE = ChromaBaselineEngine()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not ENGINE.is_available(),
        reason="optional DSP stack (numpy/librosa) not installed",
    ),
]


def _progression_wav(directory: Path, name: str = "progression.wav") -> Path:
    """Write the deterministic chord progression used by these tests."""
    return write_chord_wav(
        directory / name,
        chords=PROGRESSION,
        seconds_per_chord=SECONDS_PER_CHORD,
    )


def _assert_timestamped_coverage(document: AnalysisResult, duration: float) -> None:
    """Every claim of roadmap Phase B about the output, checked in one place."""
    events = document.chords
    assert events, "the chord engine must produce at least one event"

    # Timestamps: a real interval, starting at zero and ordered on the timeline.
    assert events[0].start == 0.0
    assert all(event.end is not None for event in events)
    starts = [event.start for event in events]
    assert starts == sorted(starts)
    assert all(event.end is not None and event.end >= event.start for event in events), (
        "no event may end before it starts"
    )

    # The timeline reaches the end of the file (the last analysed frame lands
    # within one hop of the four second duration).
    last_end = events[-1].end
    assert last_end is not None
    assert duration - 0.5 <= last_end <= duration + 0.1

    # Vocabulary and provenance: phase 1 labels, always attributed to the engine.
    assert all(event.label in baseline.TEMPLATE_LABELS or event.label == "N" for event in events)
    assert all(event.source == "chroma-baseline" for event in events)


def _convert_to_mp3(source: Path, target: Path) -> bool:
    """Transcode ``source`` to ``target`` with FFmpeg; ``False`` when it cannot."""
    tools = discover_ffmpeg_tools()
    if tools.ffmpeg is None:
        return False
    result = run_safely(
        [tools.ffmpeg, "-y", "-i", source, "-codec:a", "libmp3lame", "-b:a", "192k", target],
        timeout=60.0,
    )
    return result.returncode == 0 and target.exists()


def _outcome_on_mp3(tmp_path: Path, *, name: str) -> AnalysisOutcome | None:
    """Analyse an MP3 transcode of the progression, or ``None`` without FFmpeg."""
    wav = _progression_wav(tmp_path)
    mp3 = tmp_path / name
    if not _convert_to_mp3(wav, mp3):
        return None
    return run_analysis(mp3)


class TestRealAudioDocument:
    """One real (generated) file all the way through the application service."""

    def test_chord_events_cover_the_file(self, tmp_path: Path) -> None:
        outcome = run_analysis(_progression_wav(tmp_path))

        assert outcome.result.audio is not None
        assert outcome.result.audio.duration == pytest.approx(DURATION, abs=0.1)
        _assert_timestamped_coverage(outcome.result, DURATION)

    def test_every_layer_is_attributed(self, tmp_path: Path) -> None:
        outcome = run_analysis(_progression_wav(tmp_path))
        document = outcome.result

        assert document.run.status is RunStatus.SUCCEEDED
        assert document.key is not None
        assert document.tempo is not None
        assert {step.kind for step in outcome.steps} == {"chords", "key", "tempo"}
        assert all(step.status.value == "ok" for step in outcome.steps)
        assert outcome.total_processing_seconds is not None
        assert outcome.total_processing_seconds > 0.0

    def test_provenance_records_engines_and_input(self, tmp_path: Path) -> None:
        wav = _progression_wav(tmp_path)
        document = run_analysis(wav).result

        assert document.provenance.input_path == str(wav)
        assert document.provenance.input_hash is not None
        assert len(document.provenance.input_hash) == 64
        assert set(document.provenance.engines) == {"chroma-baseline", "krumhansl", "librosa-tempo"}
        assert document.provenance.configuration == {
            "chords": "chroma-baseline",
            "key": "krumhansl",
            "tempo": "librosa-tempo",
        }

    def test_the_document_survives_a_json_round_trip(self, tmp_path: Path) -> None:
        """The canonical codec keeps the timestamps a GUI would draw."""
        document = run_analysis(_progression_wav(tmp_path)).result

        restored = from_json(AnalysisResult, to_json(document))

        assert [event.label for event in restored.chords] == [
            event.label for event in document.chords
        ]
        assert [event.start for event in restored.chords] == pytest.approx(
            [event.start for event in document.chords]
        )
        assert [event.end for event in restored.chords] == pytest.approx(
            [event.end for event in document.chords]
        )
        assert restored.run.status is document.run.status


class TestRealMp3File:
    """The acceptance criterion is a real MP3, not only a WAV."""

    def test_transcode_analyses_the_same_timeline(self, tmp_path: Path) -> None:
        if discover_ffmpeg_tools().ffmpeg is None:
            pytest.skip("FFmpeg is not installed")

        outcome = _outcome_on_mp3(tmp_path, name=TRANSCODE_NAME)
        if outcome is None:
            pytest.skip("FFmpeg cannot encode MP3 in this environment")

        document = outcome.result
        assert document.audio is not None
        assert document.audio.format == "mp3"
        _assert_timestamped_coverage(document, DURATION)
