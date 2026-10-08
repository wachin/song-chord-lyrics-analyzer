"""The Phase D window over the real pipeline.

The unit tests prove the widgets against a fake player and a canned document.
This file proves the promise the roadmap makes for the minimal window: with the
real chord engine, a real file and (when the machine has one) the real audio
device, a user can open a song, see its waveform timeline, play it, seek, and
always see the chord for the current position - and every label on screen is the
chord ``SongSession`` claims for that instant.

Everything runs on the offscreen platform plugin, so the window is exercised
without a display; the playback half is skipped honestly on a machine with no
output device, exactly like the terminal display's integration test.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from fixtures.audio import write_chord_wav
from song_chord_lyrics_analyzer.app import SongSession
from song_chord_lyrics_analyzer.audio.playback import PlaybackState, SoundDevicePlayer
from song_chord_lyrics_analyzer.cli.main import main
from song_chord_lyrics_analyzer.engines import ChromaBaselineEngine
from song_chord_lyrics_analyzer.gui.main_window import MainWindow

pytestmark = pytest.mark.integration

if importlib.util.find_spec("PyQt6") is None:  # pragma: no cover - Qt-free machine
    pytest.skip("PyQt6 is not installed (optional 'gui' extra)", allow_module_level=True)

QtCore = pytest.importorskip("PyQt6.QtCore")
QtGui = pytest.importorskip("PyQt6.QtGui")
QtWidgets = pytest.importorskip("PyQt6.QtWidgets")

#: Eight short chords, so a few seconds of playback cross several boundaries.
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

requires_dsp = pytest.mark.skipif(
    not ChromaBaselineEngine().is_available(),
    reason="optional DSP stack (numpy/librosa) not installed",
)
requires_device = pytest.mark.skipif(
    not SoundDevicePlayer.is_available(),
    reason="no audio output device (or sounddevice is not installed)",
)


@pytest.fixture
def progression(tmp_path: Path) -> Path:
    """A generated song whose chords the real engine can hear."""
    return write_chord_wav(
        tmp_path / "progression.wav",
        chords=PROGRESSION,
        seconds_per_chord=SECONDS_PER_CHORD,
    )


@requires_dsp
def test_the_window_shows_the_real_analysis_of_a_generated_song(
    qt_app: object, progression: Path
) -> None:
    session = SongSession()
    window = MainWindow(session=session)
    window.resize(900, 520)
    window.show()
    try:
        assert window.open_file(progression) is True

        # The waveform and the chord strip come from the real file.
        peaks = window.timeline.peaks
        assert peaks is not None
        assert peaks.bucket_count >= 1
        assert max(peaks.maximums) > 0.0, "the decoded song has no signal"
        assert window.timeline.duration == pytest.approx(DURATION, abs=0.1)
        assert window.timeline.bands, "the real engine produced no chord to draw"

        shown = dict(window.panel.text_rows())
        assert shown["Chords"] != "none detected"
        assert shown["Engines"].startswith("chords=chroma-baseline")
        assert shown["Run"] in {"succeeded", "partial"}

        # Every position shows exactly the chord the session claims for it.
        for step in range(0, int(DURATION * 2) + 1):
            position = step / 2
            window.seek(position)
            claimed = session.chord_at(position)
            expected = claimed.to_label() if claimed is not None else "--"
            assert window.chord_label.text() == expected
            assert window.timeline.position == pytest.approx(position)
    finally:
        window.close()


@requires_dsp
def test_the_gui_command_opens_a_real_song_and_exits_cleanly(
    qt_app: object, progression: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole product path: ``songlab gui FILE`` -> window -> event loop."""
    reported: list[str] = []
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "warning",
        lambda *args, **kwargs: reported.append(args[-1]),
    )
    application = QtWidgets.QApplication.instance()
    QtCore.QTimer.singleShot(300, application.quit)

    assert main(["gui", str(progression)]) == 0
    assert reported == [], f"opening the song reported: {reported}"


@requires_dsp
@requires_device
def test_the_chord_on_screen_follows_the_real_playback(qt_app: object, progression: Path) -> None:
    """Play for real, refresh the window, and check every label against the session."""
    session = SongSession()
    window = MainWindow(session=session, interval=0.05)
    window.resize(900, 520)
    window.show()
    try:
        assert window.open_file(progression) is True
        window.toggle_play()
        assert session.state is PlaybackState.PLAYING

        seen: list[str] = []
        for _step in range(30):
            QtCore.QThread.msleep(50)
            frame = window.refresh()
            assert frame is not None
            claimed = session.chord_at(frame.position)
            expected = claimed.to_label() if claimed is not None else "--"
            assert frame.chord_text == expected
            assert window.chord_label.text() == expected
            seen.append(expected)

        assert session.position() > 0.2, "playback never advanced"
        assert len(set(seen)) >= 2, f"the chord never changed during playback: {seen}"
    finally:
        window.close()


@requires_dsp
def test_the_timeline_of_the_real_song_paints_offscreen(qt_app: object, progression: Path) -> None:
    session = SongSession()
    window = MainWindow(session=session)
    window.resize(800, 400)
    window.show()
    try:
        assert window.open_file(progression) is True
        window.seek(DURATION / 2)

        image = QtGui.QImage(window.timeline.size(), QtGui.QImage.Format.Format_ARGB32)
        image.fill(0)
        painter = QtGui.QPainter(image)
        window.timeline.render(painter)
        painter.end()

        colours = {
            image.pixelColor(x, y).name()
            for x in range(0, image.width(), 4)
            for y in range(0, image.height(), 4)
        }
        assert len(colours) > 2, "the real timeline painted nothing recognisable"
    finally:
        window.close()
