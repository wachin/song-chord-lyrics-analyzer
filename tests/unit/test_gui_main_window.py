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
import json
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from fixtures.audio import write_sine_wav, write_wav_bytes
from fixtures.fake_analysis import DURATION, analysis_outcome, opened_session
from fixtures.fake_player import FakePlayer
from song_chord_lyrics_analyzer.analysis import AnalysisOutcome, ProgressEvent
from song_chord_lyrics_analyzer.app import SongSession
from song_chord_lyrics_analyzer.app.persistence import edits_sidecar_path
from song_chord_lyrics_analyzer.audio.playback import PlaybackState
from song_chord_lyrics_analyzer.export import render_chordpro, render_markdown
from song_chord_lyrics_analyzer.gui.analysis_worker import ImmediateAnalysis
from song_chord_lyrics_analyzer.gui.main_window import SEEK_STEP, MainWindow, launch
from song_chord_lyrics_analyzer.utils.errors import DependencyError, InputError

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
    built = MainWindow(session=session, analysis=ImmediateAnalysis(session))
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


def _spin(seconds: float) -> None:
    """Let the event loop run for ``seconds``, like a real desktop would."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.002)


def _wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> bool:
    """Spin the event loop until ``predicate`` holds; ``False`` on timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QtWidgets.QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.002)
    return predicate()


class _GatedAnalysis:
    """An analysis the test can hold open while it inspects the window.

    It reports two progress events (a step start and a chord window), then waits
    for the test to release it - which is what makes "the window stayed
    responsive" and "progress crossed the thread boundary" assertable instead of
    timing-dependent.
    """

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls: list[dict[str, Any]] = []

    def __call__(self, path: str | Path, **options: Any) -> AnalysisOutcome:
        self.calls.append({"path": Path(path), **options})
        report = options.get("on_progress")
        if report is not None:
            report(ProgressEvent("chords", "fake-chords", 0, 1))
            report(ProgressEvent("chords", "fake-chords", 1, 3, "window 1 of 3"))
        self.entered.set()
        # The window is inspected while this waits; a wedged worker must fail the
        # test rather than hang it.
        assert self.release.wait(10.0), "the test never released the analysis"
        return analysis_outcome(path)


class _FailingAnalysis:
    """An analysis that fails with ``error`` once the test lets it go."""

    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.entered = threading.Event()

    def __call__(self, path: str | Path, **options: Any) -> AnalysisOutcome:
        self.entered.set()
        raise self.error


@pytest.fixture
def gate() -> Iterator[_GatedAnalysis]:
    """A gated analysis, always released so a failing test cannot wedge a thread."""
    gated = _GatedAnalysis()
    yield gated
    gated.release.set()


def _threaded_window(session: SongSession) -> MainWindow:
    """A shown window with the *default* runner: the real worker thread."""
    window = MainWindow(session=session)
    window.resize(900, 520)
    window.show()
    return window


@pytest.fixture(autouse=True)
def _no_window_is_left_visible(qt_app: object) -> Iterator[None]:
    """Leave no visible top-level widget behind after a test.

    ``QApplication.quit()`` closes every visible top-level window (Qt calls
    ``closeAllWindows`` for it), and a window with unsaved edits answers that
    close with a modal prompt. A window leaked by one test would therefore be
    closed during the *next* test that runs a real event loop - ``TestLaunch`` -
    and its prompt would hang the run instead of failing it.

    Hiding is the safe reset: Qt sends no close event to a hidden widget, and
    hiding never prompts, so this is correct even for a test that deliberately
    ends with edits still un-saved.
    """
    yield
    application = QtWidgets.QApplication.instance()
    assert application is not None
    for widget in application.topLevelWidgets():
        widget.hide()


@pytest.fixture
def worker_window(
    qt_app: object, gate: _GatedAnalysis, monkeypatch: pytest.MonkeyPatch
) -> Iterator[MainWindow]:
    """A shown window on the real worker thread, joined before the test ends.

    A worker must never outlive its test: the gate is released and the thread is
    allowed to finish even when an assertion failed halfway, which is what keeps
    this module free of "QThread: Destroyed while thread is still running".
    """
    window = _threaded_window(SongSession(player=FakePlayer(), analyze=gate))
    yield window
    gate.release.set()
    # A worker that ended in failure while nobody watched would open a modal
    # warning from inside this teardown, and nothing would ever answer it.
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "critical", lambda *args, **kwargs: None)
    _wait_until(lambda: not window.analysis_running)
    window.close()


def _enabled_labels(window: MainWindow) -> list[str]:
    """The labels of the enabled actions across both toolbars."""
    return [
        action.text()
        for toolbar in window.findChildren(QtWidgets.QToolBar)
        for action in toolbar.actions()
        if action.text() and action.isEnabled()
    ]


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

    def test_without_a_song_the_edit_actions_do_nothing(self, qt_app: object) -> None:
        window = MainWindow()

        assert window.edits is None
        assert window.undo_edit() is False
        assert window.redo_edit() is False
        assert window.edit_chord_at(1.0) is False
        assert window.save_edits_sidecar() is False
        assert window.lyric_menu_entries(0) == ()
        assert window.apply_lyric_choice("text", 0) is False

    def test_the_transport_offers_the_actions_a_user_expects(self, qt_app: object) -> None:
        window = MainWindow()

        assert _toolbar_texts(window) == [
            "Open...",
            "Save Edits",
            "Export document...",
            "Play",
            "Stop",
            "Back",
            "Forward",
        ]


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
        session = SongSession()
        window = MainWindow(session=session, analysis=ImmediateAnalysis(session))

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

    def test_the_chord_label_offers_that_chords_confidence(self, window: MainWindow) -> None:
        """The engine's score travels with the chord the label is showing."""
        assert window.chord_label.toolTip() == "confidence unknown"  # the fake

        window.seek(1.5)  # G: this engine reports no confidence either
        window.refresh()
        assert window.chord_label.text() == "G"
        assert window.chord_label.toolTip() == "confidence unknown"

        window.seek(DURATION)  # no chord claimed: no confidence to offer
        window.refresh()
        assert window.chord_label.text() == "--"
        assert window.chord_label.toolTip() == ""

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
        # Position 3: after Open..., Save Edits and Export document....
        assert _toolbar_texts(window)[3] == "Play"

        window.toggle_play()
        assert _toolbar_texts(window)[3] == "Pause"

        window.toggle_play()
        assert _toolbar_texts(window)[3] == "Play"

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
        window = MainWindow(session=session, analysis=ImmediateAnalysis(session))

        assert window.open_file(wav) is True
        window.toggle_play()

        assert messages and "playback" in messages[0].lower()
        assert window.state_label.text() == "stopped"


class TestTheLyricsViewFollowsTheSameClock:
    """The lyrics highlight must agree with the chord band, not with a second opinion.

    The fake document has one lyric line over each second of the song, so at
    every step both views have something to claim: the highlighted line is the
    one the presenter claims for the same playhead the chord label was drawn
    from, and where the chord band says silence the lyrics say nothing too.
    """

    def test_opening_draws_the_document_in_display_order(self, window: MainWindow) -> None:
        assert [line.text for line in window.lyrics.lines] == ["hola mundo", "adios amor"]
        assert window.lyrics.has_lyrics() is True

    def test_the_active_line_and_word_follow_the_playhead(self, window: MainWindow) -> None:
        window.seek(2.6)  # inside "adios amor": word "amor" starts at 2.5

        assert window.lyrics.active_index == 1
        assert window.lyrics.active_word == "amor"

    def test_both_views_read_the_same_clock_on_every_tick(self, window: MainWindow) -> None:
        """The one assertion that both front-end views share one clock."""
        window.toggle_play()
        _advance(window, 0.5)  # 0.5 s: "mundo" starts exactly there
        assert window.chord_label.text() == "C"
        assert window.lyrics.active_index == 0
        assert window.lyrics.active_word == "mundo"

        _advance(window, 2.0)  # 2.5 s: chord says silence, lyrics say a word
        assert window.chord_label.text() == "N"  # explicit silence, 2.0..3.0
        assert window.lyrics.active_index == 1  # "adios amor" spans 2.0..3.0
        assert window.lyrics.active_word == "amor"  # its second word starts at 2.5

    def test_a_tick_outside_any_word_clears_the_highlight(self, window: MainWindow) -> None:
        window.seek(2.6)
        assert window.lyrics.active_word is not None

        window.seek(DURATION)  # past the last line and the last chord

        assert window.lyrics.active_index is None
        assert window.lyrics.active_word is None


class TestEditingTheChordLayer:
    """Phase G: correct a chord from the timeline, undo/redo, engine intact.

    The edit tape lives in the window over the document the session opened;
    the dialog is mocked, the commands are real, and the base layer (what the
    fake analysis produced) must survive every edit untouched.
    """

    @staticmethod
    def _labels(window: MainWindow) -> list[tuple[str, float, float]]:
        return [(band.label, band.start, band.end) for band in window.timeline.bands]

    def test_an_edit_dialog_pushes_a_label_command(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked: dict[str, str] = {}

        def _dialog(*args: object, **kwargs: object) -> tuple[str, bool]:
            asked["text"] = kwargs.get("text", "")
            return "Am", True

        monkeypatch.setattr(QtWidgets.QInputDialog, "getText", _dialog)

        assert window.edit_chord_at(1.5) is True
        assert asked["text"] == "G"
        assert self._labels(window) == [
            ("C", 0.0, 1.0),
            ("Am", 1.0, 2.0),
            ("N", 2.0, 3.0),
            ("F", 3.0, 4.0),
        ]

    def test_the_engines_layer_survives_every_edit(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a, **k: ("Am", True))
        window.edit_chord_at(1.5)

        base_labels = [event.to_label() for event in window.edits.base]
        assert base_labels == ["C", "G", "N", "F"]
        assert [event.source for event in window.edits.base] == ["fake-chords"] * 4

    def test_a_cancelled_dialog_edits_nothing(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a, **k: ("Am", False))

        assert window.edit_chord_at(1.5) is False
        assert [band.label for band in window.timeline.bands] == ["C", "G", "N", "F"]
        assert window.undo_edit() is False

    def test_an_invalid_label_is_reported_and_not_applied(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        warned = _warned(monkeypatch)
        monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a, **k: ("banana", True))

        assert window.edit_chord_at(1.5) is False
        assert warned and "quality" in warned[0]
        assert [band.label for band in window.timeline.bands] == ["C", "G", "N", "F"]

    def test_a_position_without_a_chord_edits_nothing(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a, **k: ("Am", True))
        # Past the last event's end there is nothing to edit - and, crucially,
        # no dialog would open (that is why this asserts before any mock).
        assert window.edit_chord_at(DURATION + 1.0) is False
        assert window.edit_chord_at(1.0) is True  # the boundary belongs to G

    def test_undo_then_redo_round_trip(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The dialog answers per call: first G -> Am, then F -> Em.
        answers = iter([("Am", True), ("Em", True)])
        monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a, **k: next(answers))
        window.edit_chord_at(1.5)
        window.edit_chord_at(3.5)

        window.undo_edit()
        assert [band.label for band in window.timeline.bands] == ["C", "Am", "N", "F"]
        window.undo_edit()
        assert [band.label for band in window.timeline.bands] == ["C", "G", "N", "F"]

        window.redo_edit()
        assert [band.label for band in window.timeline.bands] == ["C", "Am", "N", "F"]
        window.redo_edit()
        assert [band.label for band in window.timeline.bands] == ["C", "Am", "N", "Em"]

    def test_a_push_after_undo_discards_the_redo_tape(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        answers = iter([("Am", True), ("A7", True)])
        monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a, **k: next(answers))
        window.edit_chord_at(1.5)
        window.undo_edit()
        window.edit_chord_at(3.5)

        assert window.redo_edit() is False
        assert [band.label for band in window.timeline.bands] == ["C", "G", "N", "A7"]

    def test_the_big_label_shows_the_edited_chord(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a, **k: ("Am", True))
        window.seek(1.5)  # inside "G"
        window.edit_chord_at(1.5)  # G -> Am under the playhead

        assert window.chord_label.text() == "Am"


class TestEditingTheLyricsLayer:
    """Phase G for lyrics: correct a line from the view, undo/redo, engine intact.

    The lyric commands ride the same tape as the chords, so the tests drive
    them through the same seams (``lyric_menu_entries`` for the enable states,
    ``apply_lyric_choice`` for the command), mock the dialogs the way the
    chord tests do, and always check that the fake document's lines survive
    untouched in ``edits.base_lyrics``.
    """

    @staticmethod
    def _texts(window: MainWindow) -> list[str]:
        return [line.text for line in window.lyrics.lines]

    @staticmethod
    def _spans(window: MainWindow) -> list[tuple[float | None, float | None]]:
        return [(line.start, line.end) for line in window.lyrics.lines]

    @staticmethod
    def _enabled(window: MainWindow, index: int) -> dict[str, bool]:
        return {key: on for _label, key, on in window.lyric_menu_entries(index)}

    @staticmethod
    def _reopen(qt_app: object, wav: Path) -> MainWindow:
        session, _player, _clock = opened_session(wav)
        fresh = MainWindow(session=session, analysis=ImmediateAnalysis(session))
        fresh.resize(900, 520)
        assert fresh.open_file(wav) is True
        return fresh

    def test_the_menu_states_follow_the_line_under_the_click(self, window: MainWindow) -> None:
        assert self._enabled(window, 0) == {
            "text": True,
            "set-start": True,
            "set-end": True,
            "insert": True,
            "delete": True,
        }

    def test_a_line_outside_the_document_offers_no_menu(self, window: MainWindow) -> None:
        assert window.lyric_menu_entries(2) == ()  # only two lines
        assert window.lyric_menu_entries(-1) == ()
        assert window.apply_lyric_choice("delete", 2) is False

    def test_editing_the_text_pushes_a_command_and_redraws(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked: dict[str, str] = {}

        def _dialog(*args: object, **kwargs: object) -> tuple[str, bool]:
            asked["text"] = kwargs.get("text", "")
            return "hola tierra", True

        monkeypatch.setattr(QtWidgets.QInputDialog, "getText", _dialog)

        assert window.apply_lyric_choice("text", 0) is True
        assert asked["text"] == "hola mundo"  # offered the line's current words
        assert self._texts(window) == ["hola tierra", "adios amor"]
        assert window.undo_edit() is True
        assert self._texts(window) == ["hola mundo", "adios amor"]

    def test_the_engine_lines_survive_every_lyric_edit(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            QtWidgets.QInputDialog, "getText", lambda *a, **k: ("hola tierra", True)
        )
        window.apply_lyric_choice("text", 0)
        assert window.apply_lyric_choice("delete", 1) is True

        assert window.edits is not None
        assert [line.text for line in window.edits.base_lyrics] == ["hola mundo", "adios amor"]
        assert [line.source for line in window.edits.base_lyrics] == ["fake-lyrics"] * 2

    def test_a_cancelled_dialog_edits_nothing(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a, **k: ("", False))

        assert window.apply_lyric_choice("text", 0) is False
        assert self._texts(window) == ["hola mundo", "adios amor"]
        assert window.undo_edit() is False

    def test_an_empty_line_is_reported_and_not_applied(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        warned = _warned(monkeypatch)
        monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a, **k: ("   ", True))

        assert window.apply_lyric_choice("text", 0) is False
        assert warned and "empty" in warned[0]
        assert self._texts(window) == ["hola mundo", "adios amor"]

    def test_an_impossible_timing_is_reported_and_not_applied(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        warned = _warned(monkeypatch)
        # "adios amor" spans 2.0..3.0; an end of 1.0 would end it before it starts.
        monkeypatch.setattr(QtWidgets.QInputDialog, "getDouble", lambda *a, **k: (1.0, True))

        assert window.apply_lyric_choice("set-end", 1) is False
        assert warned and "non-empty" in warned[0]
        assert self._spans(window) == [(0.0, 1.0), (2.0, 3.0)]

    def test_an_untimed_insert_is_offered_no_end_until_it_has_a_start(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a, **k: ("nueva", True))
        assert window.apply_lyric_choice("insert", 1) is True

        # Untimed: drawn after the timed lines, dimmed, end not offerable yet.
        assert self._texts(window) == ["hola mundo", "adios amor", "nueva"]
        assert window.lyrics.lines[-1].start is None
        assert self._enabled(window, 2)["set-end"] is False

        monkeypatch.setattr(QtWidgets.QInputDialog, "getDouble", lambda *a, **k: (1.5, True))
        assert window.apply_lyric_choice("set-start", 2) is True

        # 1.5 s lands between the two timed lines, so the new line moved with it.
        assert self._spans(window) == [(0.0, 1.0), (1.5, None), (2.0, 3.0)]
        assert self._enabled(window, 1)["set-end"] is True

    def test_one_tape_undoes_chords_and_lyrics_in_order(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # One dialog mock serves both layers: the chord edit asks first.
        answers = iter([("Am", True), ("hola tierra", True)])
        monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a, **k: next(answers))
        window.edit_chord_at(1.5)  # chord G -> Am
        assert window.apply_lyric_choice("text", 0) is True  # line hola mundo -> hola tierra

        window.undo_edit()  # the lyric edit goes first (LIFO)
        assert self._texts(window) == ["hola mundo", "adios amor"]
        assert [band.label for band in window.timeline.bands] == ["C", "Am", "N", "F"]

        window.undo_edit()  # then the chord edit
        assert [band.label for band in window.timeline.bands] == ["C", "G", "N", "F"]
        assert self._texts(window) == ["hola mundo", "adios amor"]

        assert window.redo_edit() is True and window.redo_edit() is True
        assert [band.label for band in window.timeline.bands] == ["C", "Am", "N", "F"]
        assert self._texts(window) == ["hola tierra", "adios amor"]

    def test_deleting_and_refilling_a_line_restores_it_as_the_users(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The chord flow's twin: delete a line, put its words back, retime it.
        assert window.apply_lyric_choice("delete", 1) is True
        assert self._texts(window) == ["hola mundo"]

        # Right-click the surviving line to insert after it (the menu only
        # ever opens on a line that exists - the stale index is refused).
        monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a, **k: ("adios amor", True))
        assert window.apply_lyric_choice("insert", 0) is True
        monkeypatch.setattr(QtWidgets.QInputDialog, "getDouble", lambda *a, **k: (2.0, True))
        assert window.apply_lyric_choice("set-start", 1) is True
        monkeypatch.setattr(QtWidgets.QInputDialog, "getDouble", lambda *a, **k: (3.0, True))
        assert window.apply_lyric_choice("set-end", 1) is True

        assert [(line.text, line.start, line.end) for line in window.lyrics.lines] == [
            ("hola mundo", 0.0, 1.0),
            ("adios amor", 2.0, 3.0),
        ]
        assert window.edits is not None
        assert window.edits.effective_lyrics[1].source == "user"
        assert window.edits.base_lyrics[1].source == "fake-lyrics"  # engine kept

        for _step in range(4):  # delete, insert, start, end - one tape
            assert window.undo_edit() is True
        assert self._texts(window) == ["hola mundo", "adios amor"]
        assert [line.source for line in window.lyrics.lines] == ["fake-lyrics"] * 2

    def test_editing_the_active_line_keeps_the_highlight_in_step(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        window.seek(0.5)  # inside "hola mundo", word "mundo"
        assert window.lyrics.active_index == 0
        assert window.lyrics.active_word == "mundo"

        monkeypatch.setattr(
            QtWidgets.QInputDialog, "getText", lambda *a, **k: ("hola tierra", True)
        )
        assert window.apply_lyric_choice("text", 0) is True

        # The highlight searches the same effective layer the view draws, so
        # an edit can never make the active line disappear from its own list.
        assert self._texts(window)[0] == "hola tierra"
        assert window.lyrics.active_index == 0
        assert window.lyrics.active_word == "mundo"  # engine word timings kept

        window.seek(2.6)
        assert window.lyrics.active_index == 1  # the edited document, still one clock

    def test_the_widgets_right_click_reaches_the_window_menu(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The whole chain a user triggers: right-click -> menu -> command.

        ``QMenu.exec`` would block offscreen, so the popup is stubbed with the
        one action the pointer would pick - everything else (the widget's
        index mapping, the signal, the window's menu rows, the dialog, the
        command) is the real code.
        """
        monkeypatch.setattr(
            QtWidgets.QInputDialog, "getText", lambda *a, **k: ("hola tierra", True)
        )
        labels: dict[str, list[str]] = {}

        def _exec(self: QtWidgets.QMenu, *args: object, **kwargs: object) -> QtGui.QAction | None:
            labels["shown"] = [action.text() for action in self.actions()]
            return next(
                (action for action in self.actions() if action.text() == "Edit text..."), None
            )

        monkeypatch.setattr(QtWidgets.QMenu, "exec", _exec)
        browser = window.lyrics.findChild(QtWidgets.QTextBrowser)
        assert browser is not None
        cursor = QtGui.QTextCursor(browser.document().findBlockByNumber(0))

        browser.customContextMenuRequested.emit(browser.cursorRect(cursor).center())

        assert labels["shown"][:5] == [
            "Edit text...",
            "Set start...",
            "Set end...",
            "Insert line...",
            "Delete line",
        ]
        assert "Undo" in labels["shown"] and "Redo" in labels["shown"]
        assert self._texts(window) == ["hola tierra", "adios amor"]  # the choice applied

    def test_a_lyric_edit_counts_as_unsaved_and_saves_to_the_sidecar(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wav = window.session.path
        assert wav is not None
        monkeypatch.setattr(
            QtWidgets.QInputDialog, "getText", lambda *a, **k: ("hola tierra", True)
        )
        assert window.apply_lyric_choice("text", 0) is True
        asked: list[str] = []

        def _record(*args: object, **kwargs: object) -> object:
            asked.append("asked")
            return QtWidgets.QMessageBox.StandardButton.Save

        monkeypatch.setattr(QtWidgets.QMessageBox, "question", _record)
        window.closeEvent(QtGui.QCloseEvent())

        assert asked  # the lyric tape differed from the last save
        sidecar = wav.with_suffix(".songlab.json")
        assert sidecar.is_file()
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        assert payload["document"]["commands"][0]["kind"] == "set-lyric-text"
        assert payload["document"]["lyrics"][0]["source"] == "fake-lyrics"

    def test_reopening_replays_the_lyric_edits(
        self,
        qt_app: object,
        wav: Path,
        window: MainWindow,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            QtWidgets.QInputDialog, "getText", lambda *a, **k: ("hola tierra", True)
        )
        assert window.apply_lyric_choice("text", 0) is True
        assert window.save_edits_sidecar() is True

        fresh = self._reopen(qt_app, wav)
        assert self._texts(fresh) == ["hola tierra", "adios amor"]
        assert fresh.edits is not None
        assert len(fresh.edits) == 1  # the tape replays, not the effective layer
        assert [line.source for line in fresh.edits.base_lyrics] == ["fake-lyrics"] * 2

        fresh.undo_edit()
        assert self._texts(fresh) == ["hola mundo", "adios amor"]  # engine answers again


class TestPersistingTheEdits:
    """Phase G closure: Ctrl+S writes the sidecar; reopening replays it.

    The flow exercises the real files in ``tmp_path``: edit, save next to the
    audio, reopen with a fresh session, and the corrected layer - not the
    engine's guess - is on the timeline again, with the engine layer still
    recoverable from the sidecar.
    """

    @staticmethod
    def _labels(window: MainWindow) -> list[str]:
        return [band.label for band in window.timeline.bands]

    @staticmethod
    def _save(window: MainWindow, monkeypatch: pytest.MonkeyPatch, label: str) -> Path:
        monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a, **k: (label, True))
        assert window.edit_chord_at(1.5) is True  # G -> label
        assert window.save_edits_sidecar() is True
        sidecar = window.session.path
        assert sidecar is not None
        return sidecar.with_suffix(".songlab.json")

    def _reopen(self, qt_app: object, wav: Path) -> MainWindow:
        session, _player, _clock = opened_session(wav)
        fresh = MainWindow(session=session, analysis=ImmediateAnalysis(session))
        fresh.resize(900, 520)
        assert fresh.open_file(wav) is True
        return fresh

    def test_save_writes_the_sidecar_next_to_the_audio(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sidecar = self._save(window, monkeypatch, "Am")

        assert sidecar.is_file()
        assert sidecar.parent == window.session.path.parent

    def test_reopening_replays_the_saved_edits(
        self,
        qt_app: object,
        wav: Path,
        window: MainWindow,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        self._save(window, monkeypatch, "Am")

        fresh = self._reopen(qt_app, wav)
        assert self._labels(fresh) == ["C", "Am", "N", "F"]
        assert fresh.edits is not None
        assert len(fresh.edits) == 1  # the tape replays, not the effective layer

    def test_the_engine_layer_is_recoverable_after_reopening(
        self,
        qt_app: object,
        wav: Path,
        window: MainWindow,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        self._save(window, monkeypatch, "Am")

        fresh = self._reopen(qt_app, wav)
        assert fresh.edits is not None
        assert [event.label for event in fresh.edits.base] == ["C", "G", "N", "F"]
        fresh.undo_edit()
        assert self._labels(fresh) == ["C", "G", "N", "F"]  # engine answers again

    def test_a_second_edit_after_reopen_saves_again(
        self,
        qt_app: object,
        wav: Path,
        window: MainWindow,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        self._save(window, monkeypatch, "Am")
        fresh = self._reopen(qt_app, wav)
        monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a, **k: ("A#7", True))
        assert fresh.edit_chord_at(3.5) is True
        assert fresh.save_edits_sidecar() is True

        third = self._reopen(qt_app, wav)
        assert self._labels(third) == ["C", "Am", "N", "A#7"]

    def test_saving_with_no_edits_does_nothing(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert window.save_edits_sidecar() is False
        assert not window.session.path.with_suffix(".songlab.json").exists()

    def test_a_corrupt_sidecar_is_reported_and_the_engine_layer_kept(
        self,
        qt_app: object,
        wav: Path,
        window: MainWindow,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sidecar = self._save(window, monkeypatch, "Am")
        sidecar.write_text("{{{not json", encoding="utf-8")
        warned = _warned(monkeypatch)

        fresh = self._reopen(qt_app, wav)
        assert self._labels(fresh) == ["C", "G", "N", "F"]  # engine layer survives
        assert warned and "JSON" in warned[0]

    def test_a_stale_sidecar_is_reported_and_the_engine_layer_kept(
        self,
        qt_app: object,
        wav: Path,
        window: MainWindow,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sidecar = self._save(window, monkeypatch, "Am")
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        payload["document"]["commands"][0]["start"] = 99.0  # address nothing
        sidecar.write_text(json.dumps(payload), encoding="utf-8")
        warned = _warned(monkeypatch)

        fresh = self._reopen(qt_app, wav)
        assert self._labels(fresh) == ["C", "G", "N", "F"]
        assert fresh.edits is not None
        assert len(fresh.edits) == 0  # the tape was reset, not silently partial
        assert warned


class TestTheChordCommandsMenu:
    """Every Phase G command is reachable from the timeline's context menu.

    The menu itself is never opened (``exec`` would block offscreen); the tests
    read the enable states through ``edit_menu_entries`` and perform the chosen
    command through ``apply_edit_choice``, exactly what the menu does between
    those two calls.
    """

    @staticmethod
    def _enabled(window: MainWindow, position: float) -> dict[str, bool]:
        return {key: enabled for _label, key, enabled in window.edit_menu_entries(position)}

    @staticmethod
    def _labels(window: MainWindow) -> list[str]:
        return [band.label for band in window.timeline.bands]

    def test_inside_a_chord_everything_but_insert_is_offered(self, window: MainWindow) -> None:
        enabled = self._enabled(window, 0.5)  # inside C

        assert enabled == {
            "edit": True,
            "split": True,
            "trim-start": True,
            "trim-end": True,
            "merge-next": True,
            "delete": True,
            "insert": False,
        }

    def test_at_a_chords_start_only_the_whole_chord_commands_are_offered(
        self, window: MainWindow
    ) -> None:
        enabled = self._enabled(window, 1.0)  # exactly G's start

        assert enabled["edit"] is True
        assert enabled["delete"] is True
        assert enabled["merge-next"] is True
        assert enabled["split"] is False  # nothing to cut at the boundary
        assert enabled["trim-start"] is False
        assert enabled["trim-end"] is False
        assert enabled["insert"] is False

    def test_in_a_gap_only_insert_is_offered(self, window: MainWindow) -> None:
        enabled = self._enabled(window, DURATION + 0.5)

        assert enabled["insert"] is True
        assert all(not value for key, value in enabled.items() if key != "insert")

    def test_split_cuts_the_chord_under_the_click(self, window: MainWindow) -> None:
        assert window.apply_edit_choice("split", 0.5) is True

        assert self._labels(window) == ["C", "C", "G", "N", "F"]
        assert [(band.start, band.end) for band in window.timeline.bands[:2]] == [
            (0.0, 0.5),
            (0.5, 1.0),
        ]

    def test_trim_start_moves_the_start_forward(self, window: MainWindow) -> None:
        assert window.apply_edit_choice("trim-start", 0.5) is True

        assert (window.timeline.bands[0].start, window.timeline.bands[0].end) == (0.5, 1.0)
        assert self._labels(window) == ["C", "G", "N", "F"]

    def test_trim_end_pulls_the_end_back(self, window: MainWindow) -> None:
        assert window.apply_edit_choice("trim-end", 0.5) is True

        assert (window.timeline.bands[0].start, window.timeline.bands[0].end) == (0.0, 0.5)
        assert self._labels(window) == ["C", "G", "N", "F"]

    def test_merge_with_next_spans_both_chords(self, window: MainWindow) -> None:
        assert window.apply_edit_choice("merge-next", 0.5) is True

        assert self._labels(window) == ["C", "N", "F"]
        assert (window.timeline.bands[0].start, window.timeline.bands[0].end) == (0.0, 2.0)

    def test_delete_removes_the_chord_under_the_click(self, window: MainWindow) -> None:
        assert window.apply_edit_choice("delete", 0.5) is True

        assert self._labels(window) == ["G", "N", "F"]

    def test_insert_asks_for_a_label_and_fills_a_gap(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Deleting G leaves the [1.0, 2.0) gap a user would fill again.
        assert window.apply_edit_choice("delete", 1.5) is True
        monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a, **k: ("Am", True))

        assert window.apply_edit_choice("insert", 1.5) is True

        band = window.timeline.bands[1]
        # Open-ended: chord_bands runs it until the next event (N at 2.0).
        assert (band.label, band.start, band.end) == ("Am", 1.5, 2.0)

    def test_insert_into_covered_time_is_reported_and_changes_nothing(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        warned = _warned(monkeypatch)
        monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a, **k: ("Am", True))

        assert window.apply_edit_choice("insert", 1.5) is False

        assert self._labels(window) == ["C", "G", "N", "F"]
        assert warned and "covered" in warned[0]

    def test_a_cancelled_insert_dialog_changes_nothing(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a, **k: ("", False))

        assert window.apply_edit_choice("insert", DURATION + 0.5) is False
        assert self._labels(window) == ["C", "G", "N", "F"]

    def test_every_menu_command_is_undoable(self, window: MainWindow) -> None:
        for choice, position in (
            ("split", 0.5),
            ("trim-start", 1.5),
            ("trim-end", 2.5),
            ("merge-next", 0.5),
            ("delete", 0.5),
        ):
            assert window.apply_edit_choice(choice, position) is True
            assert window.undo_edit() is True
        assert self._labels(window) == ["C", "G", "N", "F"]


class TestClosingWithUnsavedEdits:
    """Closing with edits beyond the last save offers Save/Cancel/Discard.

    The prompt is the difference between the tape and what was last written or
    restored, so undoing back to the saved state closes silently - the answer
    is exact, not a dirty flag that lies.
    """

    @staticmethod
    def _answer(monkeypatch: pytest.MonkeyPatch, button: object) -> None:
        monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: button)

    @staticmethod
    def _never_asks(monkeypatch: pytest.MonkeyPatch) -> list[str]:
        prompts: list[str] = []

        def _unexpected(*args: object, **kwargs: object) -> object:
            prompts.append(str(args))
            return QtWidgets.QMessageBox.StandardButton.Save

        monkeypatch.setattr(QtWidgets.QMessageBox, "question", _unexpected)
        return prompts

    @staticmethod
    def _edit(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a, **k: ("Am", True))
        assert window.edit_chord_at(1.5) is True

    def test_saving_on_close_writes_the_sidecar(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wav = window.session.path
        self._edit(window, monkeypatch)
        self._answer(monkeypatch, QtWidgets.QMessageBox.StandardButton.Save)
        assert wav is not None
        sidecar = wav.with_suffix(".songlab.json")

        window.close()

        assert sidecar.is_file()
        assert window.session.is_open is False  # the close went through

    def test_discarding_on_close_does_not_write(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wav = window.session.path
        self._edit(window, monkeypatch)
        self._answer(monkeypatch, QtWidgets.QMessageBox.StandardButton.Discard)
        assert wav is not None
        sidecar = wav.with_suffix(".songlab.json")

        window.close()

        assert not sidecar.exists()
        assert window.session.is_open is False

    def test_cancelling_on_close_keeps_the_window_open(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._edit(window, monkeypatch)
        self._answer(monkeypatch, QtWidgets.QMessageBox.StandardButton.Cancel)
        event = QtGui.QCloseEvent()

        window.closeEvent(event)

        assert event.isAccepted() is False
        assert window.session.is_open is True  # nothing was released
        assert window.edits is not None and len(window.edits) == 1

    def test_closing_without_edits_never_asks(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        prompts = self._never_asks(monkeypatch)

        window.close()

        assert prompts == []
        assert window.session.is_open is False

    def test_undoing_back_to_the_saved_state_closes_silently(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wav = window.session.path
        self._edit(window, monkeypatch)
        self._answer(monkeypatch, QtWidgets.QMessageBox.StandardButton.Save)
        window.close()  # saved: the tape is now the saved state
        # Reopen, edit again, undo back - nothing is unsaved any more.
        assert wav is not None
        assert window.open_file(wav) is True
        prompts = self._never_asks(monkeypatch)
        monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a, **k: ("Em", True))
        assert window.edit_chord_at(1.5) is True
        assert window.undo_edit() is True
        # Drive closeEvent directly: a hidden widget's close() sends no event.
        window.closeEvent(QtGui.QCloseEvent())

        assert prompts == []

    def test_redo_after_an_undo_counts_as_unsaved_again(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wav = window.session.path
        self._edit(window, monkeypatch)
        self._answer(monkeypatch, QtWidgets.QMessageBox.StandardButton.Save)
        window.close()
        assert wav is not None
        assert window.open_file(wav) is True
        monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a, **k: ("Em", True))
        assert window.edit_chord_at(1.5) is True
        assert window.undo_edit() is True
        assert window.redo_edit() is True
        asked: list[str] = []

        def _record(*args: object, **kwargs: object) -> object:
            asked.append("asked")
            return QtWidgets.QMessageBox.StandardButton.Save

        monkeypatch.setattr(QtWidgets.QMessageBox, "question", _record)
        # A hidden widget's close() sends no event; drive closeEvent directly.
        window.closeEvent(QtGui.QCloseEvent())

        assert asked  # the redo made the tape differ from the saved state again


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


class TestDocumentTransforms:
    """Phase H in the window: the whole-document chord transforms.

    As with the Phase G menus, the dialog and menus themselves are never
    opened; the tests perform the chosen command through
    ``apply_transform_choice`` and read what a user would see through
    ``transform_menu_entries`` - the same calls the wiring makes between them.
    """

    def _labels(self, window: MainWindow) -> list[str]:
        return [band.label for band in window.timeline.bands]

    def test_both_transforms_are_offered_on_an_open_song(self, window: MainWindow) -> None:
        assert window.transform_menu_entries() == (
            ("Transpose all chords...", "transpose", True),
            ("Simplify all chords", "simplify", True),
        )

    def test_nothing_is_offered_before_the_first_open(self, qt_app: object, wav: Path) -> None:
        # A session built but not shown/opened by the window yet: the edits
        # stack only exists once a file is opened.
        session, _player, _clock = opened_session(wav)
        fresh = MainWindow(session=session, analysis=ImmediateAnalysis(session))

        assert fresh.transform_menu_entries() == ()
        assert fresh.apply_transform_choice("simplify") is False

    def test_transpose_rewrites_every_band(self, window: MainWindow) -> None:
        assert window.apply_transform_choice_with_semitones(2) is True

        assert self._labels(window) == ["D", "A", "N", "G"]

    def test_a_cancelled_transpose_changes_nothing(self, window: MainWindow) -> None:
        # A semitone value of ``None`` stands in for a cancelled dialog.
        assert window.apply_transform_choice_with_semitones(None) is False

        assert self._labels(window) == ["C", "G", "N", "F"]

    def test_a_rejected_offset_is_reported_and_the_tape_untouched(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        reported: list[str] = []
        monkeypatch.setattr(window, "_report", lambda error: reported.append(error.message))

        assert window.apply_transform_choice_with_semitones(12) is False
        assert reported and "-11..+11" in reported[0]
        assert window.edits is not None and len(window.edits) == 0
        assert self._labels(window) == ["C", "G", "N", "F"]

    def test_simplify_collapses_the_layer(self, window: MainWindow) -> None:
        assert window.apply_transform_choice("simplify") is True

        # The fake layer is already triads, so the labels stay - but the tape
        # records the command and provenance proves it ran.
        assert self._labels(window) == ["C", "G", "N", "F"]
        assert window.edits is not None and len(window.edits) == 1

    def test_unknown_choice_is_a_no_op(self, window: MainWindow) -> None:
        assert window.apply_transform_choice("nonsense") is False
        assert window.edits is not None and len(window.edits) == 0

    def test_an_undone_transform_restores_the_engine_layer(self, window: MainWindow) -> None:
        window.apply_transform_choice_with_semitones(2)
        assert window.undo_edit() is True

        assert self._labels(window) == ["C", "G", "N", "F"]

    def test_the_transforms_share_the_undo_and_redo_tape(self, window: MainWindow) -> None:
        window.apply_transform_choice_with_semitones(2)
        window.apply_transform_choice("simplify")
        assert window.edits is not None and len(window.edits) == 2

        # One Ctrl+Z takes the simplify back, another the transpose.
        assert window.undo_edit() is True
        assert window.undo_edit() is True
        assert self._labels(window) == ["C", "G", "N", "F"]

        # Redo walks the same commands back on, one per keystroke (the tape
        # had two, the undone two are one redo each).
        assert window.redo_edit() is True
        assert window.edits is not None and len(window.edits) == 1

    def test_the_transforms_are_covered_by_the_close_prompt(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A transposed tape counts as unsaved work, exactly like an edit."""
        window.apply_transform_choice_with_semitones(2)
        asked: list[str] = []

        def _record(*args: object, **kwargs: object) -> object:
            asked.append("asked")
            return QtWidgets.QMessageBox.StandardButton.Discard

        monkeypatch.setattr(QtWidgets.QMessageBox, "question", _record)
        # A hidden widget's close() sends no event; drive closeEvent directly.
        window.closeEvent(QtGui.QCloseEvent())

        assert asked == ["asked"]


class TestLoadingLyricsFromAFile:
    """Phase F completed: an .lrc/.srt file becomes the song's lyric base.

    The dialog is mocked; the parse, the base swap and the tape rules are
    real: the file wins, chord work stays undoable, lyric edits of the old
    base go out with it, and Ctrl+S persists the new base like any other.
    """

    @staticmethod
    def _opened(monkeypatch: pytest.MonkeyPatch, answer: tuple[str, str]) -> None:
        monkeypatch.setattr(QtWidgets.QFileDialog, "getOpenFileName", lambda *a, **k: answer)

    @staticmethod
    def _load_action(window: MainWindow) -> QtWidgets.QAction:
        candidates = [
            action
            for toolbar in window.findChildren(QtWidgets.QToolBar)
            for action in toolbar.actions()
            if action.text() == "Load lyrics from file..."
        ]
        assert len(candidates) == 1, candidates
        return candidates[0]

    def test_the_edit_toolbar_offers_the_action_next_to_the_transforms(
        self, window: MainWindow
    ) -> None:
        edit_toolbar = window.findChildren(QtWidgets.QToolBar)[1]
        labels = [
            action.text() for action in edit_toolbar.actions() if action.text()
        ]  # separators carry no label

        assert labels == [
            "Transpose chords...",
            "Simplify chords",
            "Load lyrics from file...",
        ]

    def test_loading_is_enabled_only_once_a_song_is_open(self, qt_app: object, wav: Path) -> None:
        empty = MainWindow()
        assert self._load_action(empty).isEnabled() is False

        session, _player, _clock = opened_session(wav)
        built = MainWindow(session=session, analysis=ImmediateAnalysis(session))
        assert built.open_file(wav) is True
        assert self._load_action(built).isEnabled() is True

    def test_an_lrc_file_replaces_the_lyric_base(
        self,
        window: MainWindow,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        source = tmp_path / "song.lrc"
        source.write_text("[00:01.00]from file line\n[00:03.00]second line\n", encoding="utf-8")
        self._opened(monkeypatch, (str(source), "Timed lyrics (*.lrc *.srt);;All files (*)"))

        assert window.load_lyrics_dialog() is True

        assert [(line.text, line.start, line.end) for line in window.lyrics.lines] == [
            ("from file line", 1.0, 3.0),
            ("second line", 3.0, None),
        ]
        assert "Lyrics loaded from" in window.statusBar().currentMessage()

    def test_chord_work_stays_undoable_after_the_swap(
        self,
        window: MainWindow,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a, **k: ("Am", True))
        window.edit_chord_at(1.5)  # G -> Am on the tape
        source = tmp_path / "words.lrc"
        source.write_text("[00:00.50]only lyrics\n", encoding="utf-8")
        self._opened(monkeypatch, (str(source), "Timed lyrics (*.lrc *.srt);;All files (*)"))

        assert window.load_lyrics_dialog() is True

        assert [band.label for band in window.timeline.bands] == ["C", "Am", "N", "F"]
        assert window.undo_edit() is True  # the chord command is still on the tape
        assert [band.label for band in window.timeline.bands] == ["C", "G", "N", "F"]

    def test_lyric_edits_of_the_old_base_go_out_with_it(
        self,
        window: MainWindow,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a, **k: ("edited", True))
        window.apply_lyric_choice("text", 0)  # a lyric edit against the engine base
        assert window.edits is not None and len(window.edits.applied) == 1

        source = tmp_path / "words.lrc"
        source.write_text("[00:00.50]only lyrics\n", encoding="utf-8")
        self._opened(monkeypatch, (str(source), "Timed lyrics (*.lrc *.srt);;All files (*)"))

        assert window.load_lyrics_dialog() is True
        assert window.edits is not None and len(window.edits.applied) == 0
        assert [line.text for line in window.lyrics.lines] == ["only lyrics"]

    def test_a_cancelled_dialog_loads_nothing(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._opened(monkeypatch, ("", "Timed lyrics (*.lrc *.srt);;All files (*)"))

        assert window.load_lyrics_dialog() is False
        assert [line.text for line in window.lyrics.lines] == ["hola mundo", "adios amor"]

    def test_without_a_song_the_dialog_never_opens(
        self, qt_app: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _forbidden(*args: object, **kwargs: object) -> tuple[str, str]:
            raise AssertionError("the load dialog must not open without a song")

        monkeypatch.setattr(QtWidgets.QFileDialog, "getOpenFileName", _forbidden)

        assert MainWindow().load_lyrics_dialog() is False

    def test_a_broken_lyric_file_is_reported_and_changes_nothing(
        self,
        window: MainWindow,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        warned = _warned(monkeypatch)
        source = tmp_path / "empty.lrc"
        source.write_text("[ti:nothing]\n", encoding="utf-8")
        self._opened(monkeypatch, (str(source), "Timed lyrics (*.lrc *.srt);;All files (*)"))

        assert window.load_lyrics_dialog() is False
        assert warned and "no lyric lines" in warned[0]
        assert [line.text for line in window.lyrics.lines] == ["hola mundo", "adios amor"]

    def test_the_loaded_base_persists_with_the_next_save(
        self,
        window: MainWindow,
        wav: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        source = tmp_path / "song.lrc"
        source.write_text("[00:01.00]from file line\n", encoding="utf-8")
        self._opened(monkeypatch, (str(source), "Timed lyrics (*.lrc *.srt);;All files (*)"))
        window.load_lyrics_dialog()

        assert window.save_edits_sidecar() is True
        payload = json.loads(edits_sidecar_path(wav).read_text(encoding="utf-8"))["document"]
        assert [line["text"] for line in payload["lyrics"]] == ["from file line"]

        fresh_session, _player, _clock = opened_session(wav)
        rebuilt = MainWindow(session=fresh_session, analysis=ImmediateAnalysis(fresh_session))
        assert rebuilt.open_file(wav) is True
        assert [line.text for line in rebuilt.lyrics.lines] == ["from file line"]

    def test_a_swapped_base_alone_counts_as_unsaved_work(
        self,
        window: MainWindow,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The swap is real work even with an empty tape: the close prompt asks.

        The saved state is the tape *and* the lyric base the sidecar carries,
        so a swapped base with no command must not slip out unsaved.
        """
        source = tmp_path / "song.lrc"
        source.write_text("[00:01.00]from file line\n", encoding="utf-8")
        self._opened(monkeypatch, (str(source), "Timed lyrics (*.lrc *.srt);;All files (*)"))
        assert window.load_lyrics_dialog() is True
        assert window.edits is not None and len(window.edits) == 0  # no command at all

        asked: list[str] = []

        def _ask(*args: object, **kwargs: object) -> object:
            asked.append("asked")
            return QtWidgets.QMessageBox.StandardButton.Cancel

        monkeypatch.setattr(QtWidgets.QMessageBox, "question", _ask)
        window.closeEvent(QtGui.QCloseEvent())

        assert asked == ["asked"]
        assert window.session.is_open is True  # Cancel kept the song open

    def test_saving_the_swapped_base_closes_silently_again(
        self,
        window: MainWindow,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        source = tmp_path / "song.lrc"
        source.write_text("[00:01.00]from file line\n", encoding="utf-8")
        self._opened(monkeypatch, (str(source), "Timed lyrics (*.lrc *.srt);;All files (*)"))
        assert window.load_lyrics_dialog() is True
        assert window.save_edits_sidecar() is True

        def _forbidden(*args: object, **kwargs: object) -> object:
            raise AssertionError("a saved base must not prompt on close")

        monkeypatch.setattr(QtWidgets.QMessageBox, "question", _forbidden)
        window.closeEvent(QtGui.QCloseEvent())

        assert window.session.is_open is False  # closed with nothing lost


class TestExportingTheDocument:
    """Phase H: the save-export dialog over the exporters ``songlab export`` uses.

    The dialog is mocked, the write is real, and it goes through the same
    ``export_document()`` seam the CLI calls - so the file on disk is asserted
    against what the exporter renders for the *effective* layers, not against
    hand-written text.
    """

    @staticmethod
    def _answered(monkeypatch: pytest.MonkeyPatch, answer: tuple[str, str]) -> None:
        monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", lambda *a, **k: answer)

    @staticmethod
    def _export_action(window: MainWindow) -> QtWidgets.QAction:
        """The Export action, found where the user finds it: the toolbar."""
        candidates = [
            action
            for toolbar in window.findChildren(QtWidgets.QToolBar)
            for action in toolbar.actions()
            if action.text() == "Export document..."
        ]
        assert len(candidates) == 1, candidates
        return candidates[0]

    def test_the_toolbar_offers_the_export_action(self, window: MainWindow) -> None:
        # Between Save Edits and Play: document actions first, transport after.
        assert _toolbar_texts(window)[1:3] == ["Save Edits", "Export document..."]

    def test_export_is_enabled_only_once_a_song_is_open(self, qt_app: object, wav: Path) -> None:
        def enabled(owner: MainWindow) -> bool:
            return self._export_action(owner).isEnabled()

        empty = MainWindow()
        assert enabled(empty) is False

        session, _player, _clock = opened_session(wav)
        built = MainWindow(session=session, analysis=ImmediateAnalysis(session))
        assert built.open_file(wav) is True
        assert enabled(built) is True

    def test_the_dialog_exports_the_chordpro_sheet(
        self,
        window: MainWindow,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        target = tmp_path / "song.pro"
        self._answered(monkeypatch, (str(target), "ChordPro (*.pro *.crd)"))

        assert window.export_file_dialog() is True
        assert target.is_file()
        document, edits = window.session.document, window.edits
        assert document is not None and edits is not None
        expected = render_chordpro(document, chords=edits.effective, lyrics=edits.effective_lyrics)
        assert target.read_text(encoding="utf-8") == expected
        assert "Exported chordpro to" in window.statusBar().currentMessage()

    def test_a_cancelled_dialog_exports_nothing(
        self, window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "never-exported.pro"
        # A cancelled dialog comes back as an empty name.
        self._answered(monkeypatch, ("", "ChordPro (*.pro *.crd)"))

        assert window.export_file_dialog() is False
        # tmp_path also holds the song the fixture wrote; the target is what
        # the cancelled dialog must not have created.
        assert not target.exists()

    def test_without_a_song_the_dialog_never_opens(
        self, qt_app: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _forbidden(*args: object, **kwargs: object) -> tuple[str, str]:
            raise AssertionError("the export dialog must not open without a song")

        monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", _forbidden)

        assert MainWindow().export_file_dialog() is False

    def test_the_filter_selects_the_markdown_format(
        self,
        window: MainWindow,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        target = tmp_path / "song.md"
        self._answered(monkeypatch, (str(target), "Markdown (*.md)"))

        assert window.export_file_dialog() is True
        document, edits = window.session.document, window.edits
        assert document is not None and edits is not None
        expected = render_markdown(document, chords=edits.effective, lyrics=edits.effective_lyrics)
        assert target.read_text(encoding="utf-8") == expected

    def test_the_suffix_decides_when_the_dialog_gives_no_filter(
        self,
        window: MainWindow,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Qt's rule: the picked filter is authoritative. When it is not one
        # of ours (empty string here), the typed name keeps its format.
        target = tmp_path / "sheet-v2.md"
        self._answered(monkeypatch, (str(target), ""))

        assert window.export_file_dialog() is True
        document, edits = window.session.document, window.edits
        assert document is not None and edits is not None
        expected = render_markdown(document, chords=edits.effective, lyrics=edits.effective_lyrics)
        assert target.read_text(encoding="utf-8") == expected

    def test_the_export_carries_the_edited_layers(
        self,
        window: MainWindow,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a, **k: ("Am", True))
        window.edit_chord_at(1.5)  # G -> Am on the tape
        target = tmp_path / "song.json"
        self._answered(monkeypatch, (str(target), "JSON (*.json)"))

        assert window.export_file_dialog() is True
        payload = json.loads(target.read_text(encoding="utf-8"))
        assert [chord["label"] for chord in payload["chords"]] == ["C", "Am", "N", "F"]
        assert len(payload["lyrics"]) == 2

    def test_an_unwritable_location_is_reported_not_hidden(
        self,
        window: MainWindow,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        warned = _warned(monkeypatch)
        target = tmp_path / "no-such-dir" / "song.md"
        self._answered(monkeypatch, (str(target), "Markdown (*.md)"))

        assert window.export_file_dialog() is False
        assert warned and "Could not write" in warned[0]


class TestTheAnalysisRunsOffTheUiThread:
    """Phase K: the window keeps painting while a song is analysed.

    These tests use the real threaded runner, with an analysis the test holds
    open, so "the window stayed responsive" is asserted against a busy worker
    rather than assumed. The progress a user would see, the actions that are
    disabled meanwhile and the close that is deferred are all checked through
    the window's own public surface.
    """

    def test_open_file_returns_while_the_analysis_is_still_running(
        self, worker_window: MainWindow, wav: Path, gate: _GatedAnalysis
    ) -> None:
        assert worker_window.open_file(wav) is True  # started, not finished
        assert gate.entered.wait(5.0)
        assert worker_window.analysis_running is True
        assert worker_window.session.is_open is False  # the song is not there yet
        assert worker_window.progress.isVisible() is True
        assert "Analysing song.wav" in worker_window.statusBar().currentMessage()

    def test_the_event_loop_keeps_running_while_the_analysis_is_busy(
        self, worker_window: MainWindow, wav: Path, gate: _GatedAnalysis
    ) -> None:
        ticks: list[int] = []
        timer = QtCore.QTimer()
        timer.setInterval(1)
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start()

        assert worker_window.open_file(wav) is True
        assert gate.entered.wait(5.0)
        _spin(0.1)  # a repainting desktop would tick here, not freeze

        assert ticks, "the event loop never ran while the analysis was busy"
        assert worker_window.analysis_running is True
        timer.stop()

    def test_progress_events_cross_the_thread_to_the_window(
        self, worker_window: MainWindow, wav: Path
    ) -> None:
        assert worker_window.open_file(wav) is True

        # The service reports *window 1 of 3*: that fraction is on the bar, and
        # the detail line it computed is on the status bar, not a guess made up
        # by the window.
        assert _wait_until(lambda: worker_window.progress.maximum() == 3)
        assert worker_window.progress.value() == 1
        assert worker_window.statusBar().currentMessage() == "Analysing chords: window 1 of 3"

    def test_every_action_is_disabled_while_analysing_and_enabled_after(
        self, worker_window: MainWindow, wav: Path, gate: _GatedAnalysis
    ) -> None:
        assert worker_window.open_file(wav) is True
        assert gate.entered.wait(5.0)

        assert _enabled_labels(worker_window) == []  # nothing touches a moving session

        gate.release.set()
        # The frame is the done-handler's last word and the actions are
        # re-enabled before it, so waiting for it also settles the labels.
        assert _wait_until(lambda: worker_window.frame is not None)

        assert _enabled_labels(worker_window) == [
            "Open...",
            "Export document...",
            "Play",
            "Stop",
            "Back",
            "Forward",
            "Transpose chords...",
            "Simplify chords",
            "Load lyrics from file...",
        ]  # Save Edits stays off: an empty tape is nothing to save
        assert worker_window.progress.isVisible() is False

    def test_the_song_is_drawn_when_the_analysis_finishes(
        self, worker_window: MainWindow, wav: Path, gate: _GatedAnalysis
    ) -> None:
        assert worker_window.open_file(wav) is True

        gate.release.set()
        assert _wait_until(lambda: worker_window.frame is not None)

        window = worker_window
        assert window.session.is_open is True
        assert window.frame is not None
        assert window.chord_label.text() == "C"
        assert [(band.label, band.start, band.end) for band in window.timeline.bands] == [
            ("C", 0.0, 1.0),
            ("G", 1.0, 2.0),
            ("N", 2.0, 3.0),
            ("F", 3.0, 4.0),
        ]
        assert dict(window.panel.text_rows())["Chords"] == "4 events from fake-chords"
        assert window.analysis_running is False

    def test_a_second_song_is_refused_while_one_is_being_analysed(
        self, worker_window: MainWindow, wav: Path, gate: _GatedAnalysis
    ) -> None:
        assert worker_window.open_file(wav) is True
        assert gate.entered.wait(5.0)

        assert worker_window.open_file(wav) is False
        assert "still running" in worker_window.statusBar().currentMessage()
        assert len(gate.calls) == 1  # the second request never reached the worker

    def test_a_failed_analysis_is_reported_and_leaves_no_half_open_song(
        self, qt_app: object, wav: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        warned = _warned(monkeypatch)
        failing = _FailingAnalysis(InputError("the decoder rejected the stream"))
        window = _threaded_window(SongSession(player=FakePlayer(), analyze=failing))

        assert window.open_file(wav) is True
        assert failing.entered.wait(5.0)
        # The report is the outcome. The thread is joined before the queued
        # failure reaches the window, so ``analysis_running`` can clear a tick
        # before the dialog is captured: wait for the captured warning.
        assert _wait_until(lambda: warned and not window.analysis_running)

        assert warned and "decoder rejected" in warned[0]
        assert window.session.is_open is False
        assert window.frame is None
        assert window.progress.isVisible() is False
        assert _enabled_labels(window) == ["Open..."]  # ready for the next song
        window.close()

    def test_a_file_that_cannot_be_opened_is_refused_without_starting_work(
        self, worker_window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        warned = _warned(monkeypatch)

        assert worker_window.open_file(tmp_path / "absent.wav") is False

        assert warned and "not found" in warned[0].lower()
        assert worker_window.analysis_running is False  # no worker was ever started
        assert worker_window.progress.isVisible() is False

    def test_closing_while_analysing_defers_the_close_until_it_ends(
        self, worker_window: MainWindow, wav: Path, gate: _GatedAnalysis
    ) -> None:
        assert worker_window.open_file(wav) is True
        assert gate.entered.wait(5.0)

        event = QtGui.QCloseEvent()
        worker_window.closeEvent(event)

        # An engine call cannot be interrupted and the worker owns the session,
        # so the close is honoured when the analysis ends, not faked now.
        assert event.isAccepted() is False
        assert "Closing when the analysis finishes" in worker_window.statusBar().currentMessage()
        assert worker_window.analysis_running is True

        gate.release.set()
        # The deferred close is the outcome: the window hides itself from the
        # done-handler, which runs after the worker thread was joined.
        assert _wait_until(lambda: not worker_window.isVisible())

        assert worker_window.isVisible() is False  # the deferred close happened
        assert worker_window.session.is_open is False


class TestLaunch:
    def test_launching_without_a_file_opens_an_empty_window_and_returns(
        self, qt_app: object
    ) -> None:
        application = QtWidgets.QApplication.instance()
        QtCore.QTimer.singleShot(0, application.quit)

        assert launch() == 0
