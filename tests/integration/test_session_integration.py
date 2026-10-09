"""The Phase C session over real analysis, and real playback when possible.

``SongSession`` is the first thing that joins the pieces: the real default
registry analyses a generated file, the real decoder loads it into the real
player, and ``chord_at`` answers from the playhead. Unit tests cover the logic
with fakes; this file proves the wiring.

Needs the optional DSP stack (the chord engine) and, for the playback half, an
audio output device; both are skipped honestly when missing.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from fixtures.audio import write_chord_wav
from song_chord_lyrics_analyzer.app import SongSession
from song_chord_lyrics_analyzer.audio.playback import PlaybackState, SoundDevicePlayer
from song_chord_lyrics_analyzer.engines import ChromaBaselineEngine
from song_chord_lyrics_analyzer.engines import chroma_baseline as baseline

pytestmark = pytest.mark.integration

DURATION = 4.0
PROGRESSION: list[tuple[int, ...]] = [(0, 4, 7), (7, 11, 2), (5, 9, 0), (0, 4, 7)]


def _dsp_available() -> bool:
    return ChromaBaselineEngine().is_available()


requires_dsp = pytest.mark.skipif(
    not _dsp_available(),
    reason="optional DSP stack (numpy/librosa) not installed",
)
requires_device = pytest.mark.skipif(
    not SoundDevicePlayer.is_available(),
    reason="no audio output device (or sounddevice is not installed)",
)


def _progression(tmp_path: Path) -> Path:
    return write_chord_wav(
        tmp_path / "progression.wav",
        chords=PROGRESSION,
        seconds_per_chord=DURATION / len(PROGRESSION),
    )


@requires_dsp
def test_the_session_opens_a_song_with_the_real_pipeline(tmp_path: Path) -> None:
    session = SongSession()
    try:
        document = session.open(_progression(tmp_path))

        assert session.is_open is True
        assert document.run.status.value in {"succeeded", "partial"}
        assert document.chords, "the real chord engine must produce events"
        assert {step.kind for step in session.steps} == {"chords", "key", "tempo", "lyrics"}
        assert session.duration() == pytest.approx(DURATION, abs=0.1)
    finally:
        session.close()


@requires_dsp
def test_chord_at_covers_the_real_timeline(tmp_path: Path) -> None:
    session = SongSession()
    try:
        session.open(_progression(tmp_path))

        for position in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5):
            event = session.chord_at(position)
            assert event is not None, f"no chord event covers {position}s"
            assert event.label in baseline.TEMPLATE_LABELS or event.label == "N"
            assert event.start <= position

        assert session.chord_at(DURATION + 1.0) is None
    finally:
        session.close()


@requires_dsp
def test_the_snapshot_reports_the_real_timeline(tmp_path: Path) -> None:
    session = SongSession()
    try:
        session.open(_progression(tmp_path))
        snapshot = session.snapshot()

        assert snapshot.state is PlaybackState.STOPPED
        assert snapshot.position == 0.0
        assert snapshot.chord is not None
        assert snapshot.chord == session.chord_at(0.0)
    finally:
        session.close()


@requires_dsp
@requires_device
def test_playback_keeps_the_chord_in_step_with_the_playhead(tmp_path: Path) -> None:
    session = SongSession()
    try:
        session.open(_progression(tmp_path))
        session.play()

        deadline = time.monotonic() + 5.0
        while session.position() < 0.05 and time.monotonic() < deadline:
            time.sleep(0.02)
        assert session.position() >= 0.05, "the real playhead never moved"

        chord = session.current_chord()
        assert chord is not None
        assert chord == session.chord_at(session.position())

        session.stop()
        assert session.state is PlaybackState.STOPPED
        assert session.position() == 0.0
    finally:
        session.close()
