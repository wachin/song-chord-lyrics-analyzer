"""The display over the real pipeline, and over real playback when possible.

The unit tests prove the presenter and the loop against a fake clock. This file
proves the promise the roadmap makes for link 7: with real analysis and a real
player, the frame drawn at each refresh carries **exactly the chord the session
claims for that position** - the display cannot drift from the playhead because
it is rendered from the same snapshot.

The playback half needs an audio output device and is skipped honestly without
one (CI has no sound card); the headless half only needs the DSP stack.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from fixtures.audio import write_chord_wav
from song_chord_lyrics_analyzer.app import ConsoleDisplay, DisplayFrame, SongSession, follow
from song_chord_lyrics_analyzer.audio.playback import PlaybackState, SoundDevicePlayer
from song_chord_lyrics_analyzer.engines import ChromaBaselineEngine
from song_chord_lyrics_analyzer.engines import chroma_baseline as baseline

pytestmark = pytest.mark.integration

#: Eight short chords, so a few seconds of real playback cross several boundaries.
DURATION = 4.8
SECONDS_PER_CHORD = 0.6
PROGRESSION: list[tuple[int, ...]] = [
    (0, 4, 7),  # C
    (7, 11, 2),  # G
    (9, 0, 4),  # Am
    (5, 9, 0),  # F
    (0, 4, 7),  # C
    (7, 11, 2),  # G
    (5, 9, 0),  # F
    (0, 4, 7),  # C
]


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


class _Recorder(ConsoleDisplay):
    """A console display that keeps both the frames and the text it drew."""

    def __init__(self) -> None:
        self.stream = io.StringIO()
        super().__init__(self.stream, inline=False)
        self.frames: list[DisplayFrame] = []

    @property
    def text(self) -> str:
        """Everything written so far."""
        return self.stream.getvalue()

    def write(self, frame: DisplayFrame) -> None:
        self.frames.append(frame)
        super().write(frame)


def _progression(tmp_path: Path) -> Path:
    return write_chord_wav(
        tmp_path / "progression.wav",
        chords=PROGRESSION,
        seconds_per_chord=SECONDS_PER_CHORD,
    )


@requires_dsp
def test_the_frame_at_a_position_carries_the_chord_the_session_claims(tmp_path: Path) -> None:
    """The display is a projection of the session, never a second opinion."""
    session = SongSession()
    try:
        session.open(_progression(tmp_path))
        display = _Recorder()

        for position in (0.0, 0.5, 1.0, 2.0, 3.0, 4.0, DURATION):
            session.seek(position)
            frame = display.show(session.snapshot())

            claimed = session.chord_at(position)
            if claimed is None:
                assert frame.chord_text == "--"
            else:
                assert frame.chord is claimed
                assert frame.chord_text == claimed.to_label()
            assert frame.chord_text in {*baseline.TEMPLATE_LABELS, "N", "--", "?"}

        assert display.text.count("[") == 7
    finally:
        session.close()


@requires_dsp
def test_the_real_analysis_fills_the_display_across_the_track(tmp_path: Path) -> None:
    """A display with holes is not a product; the real engine must fill the line."""
    session = SongSession()
    try:
        session.open(_progression(tmp_path))
        display = _Recorder()
        positions = [index * 0.4 for index in range(int(DURATION / 0.4))]
        for position in positions:
            session.seek(position)
            display.show(session.snapshot())

        claimed = [frame for frame in display.frames if frame.chord_text != "--"]
        assert len(claimed) >= len(display.frames) - 1
    finally:
        session.close()


@requires_dsp
@requires_device
def test_the_display_updates_while_the_real_song_plays(tmp_path: Path) -> None:
    session = SongSession()
    try:
        session.open(_progression(tmp_path))
        display = _Recorder()
        session.play()
        assert session.state is PlaybackState.PLAYING

        frames = follow(session, display, interval=0.05, max_frames=60)

        assert frames == 60
        positions = [frame.position for frame in display.frames]
        assert positions == sorted(positions), "the playhead must never go backwards"
        assert positions[-1] > 0.5, "the display never followed playback"

        # Every frame shows the chord claimed for its own position.
        for frame in display.frames:
            claimed = session.chord_at(frame.position)
            if claimed is None:
                assert frame.chord_text == "--"
            else:
                assert frame.chord_text == claimed.to_label()

        labels = {frame.chord_text for frame in display.frames}
        assert len(labels) >= 2, f"the chord never changed during playback: {labels}"
        assert len(display.text.splitlines()) == len(display.frames)
    finally:
        session.close()
