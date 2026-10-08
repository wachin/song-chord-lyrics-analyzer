"""The Phase D window: one song, its waveform, its chords, its playhead.

The window is driven the way a user drives it - open a file, press the transport,
click the timeline - but through the fake player and the fake clock the session
already accepts, so every assertion is exact instead of timing-dependent. The
central promise is the one the terminal display also makes: the chord on screen
at each refresh is the chord the session claims for the position of that same
refresh, so the window cannot drift from the playhead.

Everything runs on the offscreen platform plugin and reads the widgets a user
would touch (labels, the toolbar, the timeline), never a private attribute;
without PyQt6 installed the whole module skips, which is what keeps the core test
matrix Qt-free.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from fixtures.audio import write_sine_wav, write_wav_bytes
from fixtures.fake_analysis import DURATION, analysis_outcome, opened_session
from fixtures.fake_player import FakePlayer
from song_chord_lyrics_analyzer.app import SongSession
from song_chord_lyrics_analyzer.audio.playback import PlaybackState
from song_chord_lyrics_analyzer.gui.main_window import SEEK_STEP, MainWindow, launch
from song_chord_lyrics_analyzer.utils.errors import DependencyError

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PyQt6") is None,
    reason="PyQt6 is not installed (optional 'gui' extra)",
)

QtCore = pytest.importorskip("PyQt6.QtCore")
QtGui = pytest.importorskip("PyQt6.QtGui")
QtTest = pytest.importorskip("PyQt6.QtTest")
QtWidgets = pytest.importorskip("PyQt6.QtWidgets")


@pytest.fixture
def wav(tmp_path: Path) -> Path:
    """The four second song the fake analysis describes."""
    return write_sine_wav(tmp_path / "song.wav", seconds=DURATION, channels=1)


@pytest.fixture
def window(qt_app: object, wav: Path) -> MainWindow:
    """An open, shown window whose session runs on the fake player."""
    session, _player, _clock = opened_session(wav)
    built = MainWindow(session=session)
    built.resize(900, 520)
    built.show()
    assert built.open_file(wav) is True
    return built


def _player(window: MainWindow) -> FakePlayer:
    """The fake player behind the window's session."""
    player = window.session.player
    assert isinstance(player, FakePlayer), player
    return player


def _advance(window: MainWindow, seconds: float) -> None:
    """Move the fake clock and refresh once, like a single timer tick."""
    _player(window).advance(seconds)
    window.refresh()


def _toolbar_texts(window: MainWindow) -> list[str]:
    """The labels of the transport buttons, in order."""
    toolbar = window.findChild(QtWidgets.QToolBar)
    assert toolbar is not None
    return [action.text() for action in toolbar.actions()]


def _click_timeline(window: MainWindow, fraction: float) -> None:
    """Click the timeline at ``fraction`` of its width."""
    timeline = window.timeline
    x = max(0, min(timeline.width() - 1, int(timeline.width() * fraction)))
    QtTest.QTest.mouseClick(
        timeline,
        QtCore.Qt.MouseButton.LeftButton,
        pos=QtCore.QPoint(x, timeline.height() // 2),
    )


def _warned(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Capture dialogs instead of opening them, so tests stay headless."""
    messages: list[str] = []
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "warning",
        lambda *args, **kwargs: messages.append(args[-1]),
    )
    return messages


class TestAnEmptyWindow:
    def test_it_starts_with_no_song_and_no_frame(self, qt_app: object) -> None:
        window = MainWindow()

        assert window.session.is_open is False
        assert window.frame is None
        assert window.chord_label.text() == "--"
        assert window.timeline.duration == 0.0
        assert window.timeline.peaks is None
        assert window.panel.text_rows() == ()

    def test_without_a_song_the_playback_actions_do_nothing(self, qt_app: object) -> None:
        window = MainWindow()

        window.toggle_play()
        window.stop()
        window.seek(1.0)
        window.seek_by(SEEK_STEP)

        assert window.frame is None

    def test_the_transport_offers_the_actions_a_user_expects(self, qt_app: object) -> None:
        window = MainWindow()

        assert _toolbar_texts(window) == ["Open...", "Play", "Stop", "Back", "Forward"]


class TestOpeningASong:
    def test_opening_draws_the_first_frame(self, window: MainWindow) -> None:
        assert window.session.is_open is True
        assert window.frame is not None
        assert window.chord_label.text() == "C"
        assert window.state_label.text() == "stopped"
        assert window.time_label.text() == "00:00:00.000 / 00:00:04.000"

    def test_the_timeline_gets_the_waveform_the_bands_and_the_length(
        self, window: MainWindow
    ) -> None:
        peaks = window.timeline.peaks
        assert peaks is not None
        assert peaks.bucket_count >= 1
        assert window.timeline.duration == pytest.approx(DURATION)
        assert [(band.label, band.start, band.end) for band in window.timeline.bands] == [
            ("C", 0.0, 1.0),
            ("G", 1.0, 2.0),
            ("N", 2.0, 3.0),
            ("F", 3.0, 4.0),
        ]

    def test_the_panel_shows_what_the_analysis_found(self, window: MainWindow) -> None:
        shown = dict(window.panel.text_rows())

        assert shown["File"] == "song.wav"
        assert shown["Chords"] == "4 events from fake-chords"
        assert shown["Key"] == "C major"
        assert shown["Tempo"] == "120.0 BPM"
        assert shown["Engines"] == "chords=fake-chords, key=fake-key"
        assert shown["Skipped"] == "tempo (fake-tempo): not available"

    def test_a_file_that_cannot_be_opened_is_reported_and_changes_nothing(
        self, qt_app: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        messages = _warned(monkeypatch)
        window = MainWindow()

        assert window.open_file(write_wav_bytes(tmp_path / "corrupt.wav")) is False
        assert window.session.is_open is False
        assert window.frame is None
        assert messages and "not" in messages[0].lower()

    def test_the_waveform_is_redrawn_at_the_new_width_on_resize(self, window: MainWindow) -> None:
        before = window.timeline.peaks
        assert before is not None

        window.resize(400, 300)
        window.refresh()
        resized = window.timeline.peaks

        assert resized is not None
        assert resized.bucket_count == max(1, window.timeline.width())
        assert resized.bucket_count != before.bucket_count


class TestTheChordFollowsThePlayhead:
    def test_playing_moves_the_chord_from_one_event_to_the_next(self, window: MainWindow) -> None:
        window.toggle_play()
        assert window.state_label.text() == "playing"

        _advance(window, 1.5)
        assert window.chord_label.text() == "G"
        assert window.time_label.text() == "00:00:01.500 / 00:00:04.000"

        _advance(window, 1.0)
        assert window.chord_label.text() == "N"

        _advance(window, 1.0)
        assert window.chord_label.text() == "F"

    def test_every_drawn_frame_carries_the_chord_the_session_claims(
        self, window: MainWindow
    ) -> None:
        """The one assertion that says the window cannot drift from the playhead."""
        window.toggle_play()
        drawn: set[str] = set()

        for _step in range(12):
            _advance(window, 0.3)
            frame = window.frame
            assert frame is not None
            claimed = window.session.chord_at(frame.position)
            expected = claimed.to_label() if claimed is not None else "--"
            assert frame.chord_text == expected
            assert window.chord_label.text() == expected
            assert window.timeline.position == pytest.approx(frame.position)
            drawn.add(window.chord_label.text())

        assert drawn == {"C", "G", "N", "F"}, drawn

    def test_pausing_freezes_the_playhead_and_the_label(self, window: MainWindow) -> None:
        window.toggle_play()
        _advance(window, 1.0)
        window.pause()

        assert window.state_label.text() == "paused"
        assert window.chord_label.text() == "G"
        assert window.session.position() == pytest.approx(1.0)
        assert window.time_label.text() == "00:00:01.000 / 00:00:04.000"

    def test_stopping_returns_the_playhead_to_the_start(self, window: MainWindow) -> None:
        window.toggle_play()
        _advance(window, 2.5)
        window.stop()

        assert window.frame is not None
        assert window.frame.position == 0.0
        assert window.chord_label.text() == "C"
        assert window.state_label.text() == "stopped"

    def test_the_play_button_reports_what_it_will_do_next(self, window: MainWindow) -> None:
        assert _toolbar_texts(window)[1] == "Play"

        window.toggle_play()
        assert _toolbar_texts(window)[1] == "Pause"

        window.toggle_play()
        assert _toolbar_texts(window)[1] == "Play"

    def test_a_missing_audio_device_is_reported_not_hidden(
        self, qt_app: object, wav: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        messages = _warned(monkeypatch)

        class MutedPlayer:
            """A player whose device cannot be opened."""

            name = "muted"

            def load(self, path: str | Path, *, mono: bool = False) -> None:
                return None

            def play(self) -> None:
                raise DependencyError(
                    "Audio playback needs sounddevice and numpy, which are not available.",
                    hint="Install the optional playback backend.",
                )

            def pause(self) -> None: ...

            def stop(self) -> None: ...

            def seek(self, position: float) -> None: ...

            def position(self) -> float:
                return 0.0

            def duration(self) -> float:
                return 0.0

            @property
            def state(self) -> PlaybackState:
                return PlaybackState.STOPPED

            def close(self) -> None: ...

        session = SongSession(
            player=MutedPlayer(),  # type: ignore[arg-type]
            analyze=lambda path, **options: analysis_outcome(path),
        )
        window = MainWindow(session=session)

        assert window.open_file(wav) is True
        window.toggle_play()

        assert messages and "playback" in messages[0].lower()
        assert window.state_label.text() == "stopped"


class TestSeeking:
    def test_a_click_on_the_timeline_seeks_to_that_position(self, window: MainWindow) -> None:
        _click_timeline(window, 0.625)

        assert window.frame is not None
        assert window.frame.position == pytest.approx(2.5, abs=0.05)
        assert window.chord_label.text() == "N"
        assert window.timeline.position == pytest.approx(window.frame.position)
        assert window.time_label.text().endswith("/ 00:00:04.000")

    def test_a_click_at_the_far_right_reaches_the_last_event(self, window: MainWindow) -> None:
        _click_timeline(window, 1.0)

        assert window.frame is not None
        assert window.frame.position > DURATION - 0.1
        assert window.chord_label.text() == "F"

    def test_seeking_past_the_last_event_shows_no_chord(self, window: MainWindow) -> None:
        window.seek(DURATION)

        assert window.frame is not None
        assert window.frame.position == pytest.approx(DURATION)
        assert window.chord_label.text() == "--"

    def test_the_transport_moves_the_playhead_by_a_step_and_clamps(
        self, window: MainWindow
    ) -> None:
        window.seek(1.0)
        window.seek_by(-SEEK_STEP)
        assert window.frame is not None
        assert window.frame.position == 0.0
        assert window.chord_label.text() == "C"

        # Forward from the start would pass the end of this four second song.
        window.seek_by(SEEK_STEP)
        assert window.frame.position == pytest.approx(DURATION)
        assert window.chord_label.text() == "--"


class TestDrawing:
    def test_the_timeline_paints_waveform_chords_and_playhead_offscreen(
        self, window: MainWindow
    ) -> None:
        """Painting must work on a machine with no screen and no sound card."""
        window.seek(1.2)
        image = QtGui.QImage(window.timeline.size(), QtGui.QImage.Format.Format_ARGB32)
        image.fill(0)
        painter = QtGui.QPainter(image)
        window.timeline.render(painter)
        painter.end()

        colours = {
            image.pixelColor(x, y).name()
            for x in range(0, image.width(), 5)
            for y in range(0, image.height(), 5)
        }
        assert len(colours) > 1, "the timeline painted nothing"

    def test_the_window_renders_as_a_whole(self, window: MainWindow) -> None:
        image = QtGui.QImage(window.size(), QtGui.QImage.Format.Format_ARGB32)
        image.fill(0)
        painter = QtGui.QPainter(image)
        window.render(painter)
        painter.end()

        assert image.width() > 0

    def test_a_closed_window_releases_the_session(self, window: MainWindow) -> None:
        player = _player(window)

        window.close()

        assert player.closed is True


class TestLaunch:
    def test_launching_without_a_file_opens_an_empty_window_and_returns(
        self, qt_app: object
    ) -> None:
        application = QtWidgets.QApplication.instance()
        QtCore.QTimer.singleShot(0, application.quit)

        assert launch() == 0
