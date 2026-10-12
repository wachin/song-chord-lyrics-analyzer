"""The minimal Phase D window: one song, its waveform, its chords, its playhead.

This is the smallest desktop application around the Phase C slice, and it is
built to stay that small:

* it talks to :class:`~song_chord_lyrics_analyzer.app.session.SongSession` and to
  the presenters in :mod:`song_chord_lyrics_analyzer.app` only - no engine, no
  numpy, no ``librosa``, no ``analysis/`` internals, so the window cannot
  disagree with the CLI about what is sounding;
* the refresh is one ``snapshot()`` per timer tick turned into a
  :class:`~song_chord_lyrics_analyzer.app.display.DisplayFrame`, exactly like the
  terminal display, and :meth:`MainWindow.refresh` is public so a test can drive
  it deterministically instead of waiting for a clock;
* the widgets hold no synchronization logic: the chord label comes from the
  frame, the timeline from :mod:`song_chord_lyrics_analyzer.gui.timeline` and the
  side panel from :mod:`song_chord_lyrics_analyzer.gui.analysis_panel`.

Playback comes from the session's own player, so ``songlab gui`` and
``songlab play`` are the same audio path.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from PyQt6.QtCore import QPoint, Qt, QTimer
from PyQt6.QtGui import QAction, QCloseEvent, QKeySequence, QResizeEvent
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from song_chord_lyrics_analyzer.app import (
    DEFAULT_REFRESH_INTERVAL,
    DisplayFrame,
    SongSession,
    chord_bands,
    frame_from,
    summarize,
)
from song_chord_lyrics_analyzer.app.editing import CommandStack, SetChordLabel
from song_chord_lyrics_analyzer.app.persistence import (
    edits_sidecar_path,
    load_edits,
    rebuild_stack,
)
from song_chord_lyrics_analyzer.app.persistence import (
    save_edits as save_edits_document,
)
from song_chord_lyrics_analyzer.audio.playback import PlaybackState
from song_chord_lyrics_analyzer.gui.analysis_panel import AnalysisPanel
from song_chord_lyrics_analyzer.gui.lyrics_view import LyricsWidget
from song_chord_lyrics_analyzer.gui.timeline import TimelineWidget
from song_chord_lyrics_analyzer.utils.errors import SongLabError

__all__ = ["AUDIO_FILTER", "AUDIO_SUFFIXES", "MainWindow", "launch"]

#: Audio file extensions the Open dialog offers. Kept as one list so the dialog
#: and any future validation agree on what "an audio file" means.
AUDIO_SUFFIXES: tuple[str, ...] = (
    "wav",
    "flac",
    "ogg",
    "oga",
    "opus",
    "aiff",
    "aif",
    "m4a",
    "aac",
    "wma",
    "mp3",
)

AUDIO_FILTER = "Audio (" + " ".join(f"*.{suffix}" for suffix in AUDIO_SUFFIXES) + ");;All files (*)"

#: Seek step of the back/forward actions, in seconds.
SEEK_STEP = 5.0


class MainWindow(QMainWindow):
    """The application window: open a song, play it, seek, watch the chord.

    Args:
        session: The application session to drive. Defaults to a new
            :class:`SongSession`, which owns its player; tests inject a session
            with a fake player and a fake analysis.
        engines: Optional ``kind -> engine name`` overrides for the analysis.
        input_hash: Whether opening a file records its SHA-256 in provenance.
        interval: Seconds between two refreshes of the widgets.
        parent: Qt parent, for embedding.
    """

    def __init__(
        self,
        session: SongSession | None = None,
        *,
        engines: Mapping[str, str] | None = None,
        input_hash: bool = True,
        interval: float = DEFAULT_REFRESH_INTERVAL,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session if session is not None else SongSession()
        self._engines = dict(engines or {})
        self._input_hash = input_hash
        self._frame: DisplayFrame | None = None
        self._bucket_count = 0
        self._ready = False
        self._edits: CommandStack | None = None

        self.setWindowTitle("Song Chord Lyrics Analyzer")
        self.resize(960, 560)
        self._build_actions()
        self._build_widgets()

        self._timer = QTimer(self)
        self._timer.setInterval(max(1, int(interval * 1000)))
        self._timer.timeout.connect(self.refresh)
        self._ready = True

    # -- public state ------------------------------------------------------

    @property
    def session(self) -> SongSession:
        """The session this window drives."""
        return self._session

    @property
    def frame(self) -> DisplayFrame | None:
        """The last frame drawn, or ``None`` before the first refresh."""
        return self._frame

    @property
    def chord_label(self) -> QLabel:
        """The label showing the chord under the playhead."""
        return self._chord_label

    @property
    def time_label(self) -> QLabel:
        """The label showing the playhead and the track length."""
        return self._time_label

    @property
    def state_label(self) -> QLabel:
        """The label showing whether playback is stopped, playing or paused."""
        return self._state_label

    @property
    def timeline(self) -> TimelineWidget:
        """The waveform, chord strip and playhead widget."""
        return self._timeline

    @property
    def panel(self) -> AnalysisPanel:
        """The analysis summary panel."""
        return self._panel

    @property
    def lyrics(self) -> LyricsWidget:
        """The lyrics view bound to the same clock as the chord band."""
        return self._lyrics

    # -- construction ------------------------------------------------------

    def _build_actions(self) -> None:
        self._open_action = QAction("Open...", self)
        self._open_action.setShortcut(QKeySequence.StandardKey.Open)
        self._open_action.triggered.connect(self.choose_file)

        self._play_action = QAction("Play", self)
        self._play_action.setShortcut(QKeySequence("Space"))
        self._play_action.triggered.connect(self.toggle_play)

        self._stop_action = QAction("Stop", self)
        self._stop_action.triggered.connect(self.stop)

        self._back_action = QAction("Back", self)
        self._back_action.setShortcut(QKeySequence("Left"))
        self._back_action.triggered.connect(lambda: self.seek_by(-SEEK_STEP))

        self._forward_action = QAction("Forward", self)
        self._forward_action.setShortcut(QKeySequence("Right"))
        self._forward_action.triggered.connect(lambda: self.seek_by(SEEK_STEP))

        # Ctrl+S persists the edit tape to the sidecar next to the audio, so
        # reopening the song (or the machine) finds the corrections again.
        self._save_action = QAction("Save Edits", self)
        self._save_action.setShortcut(QKeySequence.StandardKey.Save)
        self._save_action.triggered.connect(self.save_edits_sidecar)

        # Phase G: edit the chord under a clicked band; Ctrl+Z/Ctrl+Shift+Z
        # undo and redo the edits the same way every editor does.
        self._undo_action = QAction("Undo", self)
        self._undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self._undo_action.triggered.connect(self.undo_edit)

        self._redo_action = QAction("Redo", self)
        self._redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self._redo_action.triggered.connect(self.redo_edit)

        toolbar = self.addToolBar("Transport")
        assert toolbar is not None  # always created by QMainWindow
        toolbar.setMovable(False)
        for action in (
            self._open_action,
            self._save_action,
            self._play_action,
            self._stop_action,
            self._back_action,
            self._forward_action,
        ):
            toolbar.addAction(action)

    def _build_widgets(self) -> None:
        self._chord_label = QLabel("--")
        self._chord_label.setObjectName("chord")
        chord_font = self._chord_label.font()
        chord_font.setPointSize(chord_font.pointSize() + 18)
        chord_font.setBold(True)
        self._chord_label.setFont(chord_font)
        self._chord_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._chord_label.setMinimumWidth(120)

        self._time_label = QLabel("--:--:--.--- / --:--:--.---")
        self._state_label = QLabel(PlaybackState.STOPPED.value)

        header = QHBoxLayout()
        header.addWidget(self._chord_label, 1)
        transport = QVBoxLayout()
        transport.addWidget(self._time_label, alignment=Qt.AlignmentFlag.AlignRight)
        transport.addWidget(self._state_label, alignment=Qt.AlignmentFlag.AlignRight)
        header.addLayout(transport)

        self._timeline = TimelineWidget()
        self._timeline.seek_requested.connect(self.seek)
        self._timeline.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._timeline.customContextMenuRequested.connect(self._show_edit_menu)
        self._lyrics = LyricsWidget()
        self._panel = AnalysisPanel()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._timeline)
        splitter.addWidget(self._lyrics)
        splitter.addWidget(self._panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([520, 260, 180])

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addLayout(header)
        layout.addWidget(splitter, 1)
        self.setCentralWidget(central)

    # -- opening a song ----------------------------------------------------

    def choose_file(self) -> None:
        """Ask for a file and open it."""
        chosen, _selected = QFileDialog.getOpenFileName(
            self, "Open an audio file", "", AUDIO_FILTER
        )
        if chosen:
            self.open_file(Path(chosen))

    def open_file(self, path: str | Path) -> bool:
        """Analyse and load ``path`` into the window.

        Args:
            path: The audio file to open.

        Returns:
            ``True`` when the song is open and drawn; ``False`` when it could not
            be opened, in which case the reason was already reported to the user.
        """
        self._timer.stop()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            document = self._session.open(
                path,
                engines=self._engines or None,
                input_hash=self._input_hash,
            )
            # A fresh song starts with a fresh edit tape over its engine layer,
            # then any sidecar saved for this file replays over that base.
            self._edits = CommandStack(document.chords if document is not None else [])
            self._restore_saved_edits(Path(path))
            self._populate_timeline()
            self._lyrics.set_document(tuple(document.lyrics) if document is not None else ())
            self._panel.set_rows(summarize(document, steps=self._session.steps))
        except SongLabError as error:
            self._report(error)
            return False
        finally:
            QApplication.restoreOverrideCursor()
        self._update_edit_actions()
        self.refresh()
        self._timer.start()
        return True

    def _populate_timeline(self) -> None:
        """Draw the waveform and the chord strip of the open song.

        The chord strip draws the *effective* layer (engine + the user's
        edits), never the document's raw list, so every edit is on screen the
        moment its command is pushed.
        """
        duration = self._session.duration()
        width = max(1, self._timeline.width())
        self._bucket_count = width
        self._timeline.set_peaks(self._session.waveform_peaks(buckets=width))
        chords = self._edits.effective if self._edits is not None else []
        self._timeline.set_bands(chord_bands(chords, duration=duration))
        self._timeline.set_duration(duration)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        """Redraw the waveform at the new width; peaks are cached per width."""
        super().resizeEvent(event)
        if not self._ready or not self._session.is_open:
            return
        if self._bucket_count != max(1, self._timeline.width()):
            self._populate_timeline()
            self.refresh()

    # -- playback ----------------------------------------------------------

    def toggle_play(self) -> None:
        """Play when stopped or paused, pause when playing."""
        if not self._session.is_open:
            return
        if self._session.state is PlaybackState.PLAYING:
            self._session.pause()
        else:
            try:
                self._session.play()
            except SongLabError as error:
                self._report(error)
                return
        self.refresh()

    def play(self) -> None:
        """Start or resume playback."""
        if self._session.is_open and self._session.state is not PlaybackState.PLAYING:
            self.toggle_play()

    def pause(self) -> None:
        """Pause playback, keeping the playhead."""
        if self._session.state is PlaybackState.PLAYING:
            self._session.pause()
            self.refresh()

    def stop(self) -> None:
        """Stop playback and return the playhead to the start."""
        if not self._session.is_open:
            return
        self._session.stop()
        self.refresh()

    def seek(self, position: float) -> None:
        """Move the playhead to ``position`` seconds and redraw it."""
        if not self._session.is_open:
            return
        self._session.seek(position)
        self.refresh()

    def seek_by(self, seconds: float) -> None:
        """Move the playhead by ``seconds`` from where it is now."""
        if self._frame is None:
            return
        self.seek(self._frame.position + seconds)

    # -- editing (Phase G) -------------------------------------------------

    @property
    def edits(self) -> CommandStack | None:
        """The edit tape of the open song, or ``None`` before the first open."""
        return self._edits

    def edit_chord_at(self, position: float) -> bool:
        """Ask for a new label for the chord covering ``position`` seconds.

        The command is pushed on the edit tape; the engine's output is
        untouched and the strip is redrawn from the effective layer. No chord
        there, no song open, or a cancelled dialog is a no-op.

        Args:
            position: The playhead position whose chord is edited, in seconds.

        Returns:
            ``True`` when the edit was applied.
        """
        if self._edits is None:
            return False
        event = self._edits.effective_chord_at(position)
        if event is None:
            return False
        label, accepted = QInputDialog.getText(
            self,
            "Edit chord",
            f"New label for the chord at {event.start:.2f} s (now {event.to_label()}):",
            text=event.label if event.label != "?" else "",
        )
        if not accepted:
            return False
        try:
            self._edits.push(SetChordLabel(event.start, label))
        except SongLabError as error:
            self._report(error)
            return False
        self._populate_timeline()
        self._update_edit_actions()
        self.refresh()
        return True

    def _show_edit_menu(self, pos: QPoint) -> None:
        """The timeline's context menu: edit the chord, undo, redo."""
        menu = QMenu(self)
        edit_here = menu.addAction("Edit chord here...")
        if edit_here is None or self._edits is None:  # pragma: no cover - defensive
            return
        menu.addSeparator()
        assert self._undo_action is not None and self._redo_action is not None
        menu.addAction(self._undo_action)
        menu.addAction(self._redo_action)
        chords_live = self._edits.effective_chord_at(self._timeline.seconds_at(pos.x())) is not None
        edit_here.setEnabled(chords_live)
        chosen = menu.exec(self._timeline.mapToGlobal(pos))
        if chosen == edit_here and chords_live:
            self.edit_chord_at(self._timeline.seconds_at(pos.x()))

    def undo_edit(self) -> bool:
        """Take the last edit back; ``False`` when there is nothing to undo."""
        if self._edits is None or self._edits.undo() is None:
            return False
        self._populate_timeline()
        self._update_edit_actions()
        self.refresh()
        return True

    def redo_edit(self) -> bool:
        """Reapply the last undone edit; ``False`` when there is nothing to redo."""
        if self._edits is None or self._edits.redo() is None:
            return False
        self._populate_timeline()
        self._update_edit_actions()
        self.refresh()
        return True

    def _update_edit_actions(self) -> None:
        """Enable Undo/Redo/Save only when the tape can serve them."""
        undo, redo, save = self._undo_action, self._redo_action, self._save_action
        assert undo is not None and redo is not None and save is not None
        undo.setEnabled(self._edits is not None and self._edits.can_undo)
        redo.setEnabled(self._edits is not None and self._edits.can_redo)
        save.setEnabled(self._edits is not None and len(self._edits) > 0)

    # -- persistence (Phase G) --------------------------------------------

    def save_edits_sidecar(self) -> bool:
        """Write the edit tape to the song's sidecar; ``False`` when nothing to save.

        The sidecar is the sibling ``song.songlab.json``: the engine layer plus
        the commands the user pushed. A failed save is reported, never silent.

        Returns:
            ``True`` when the edits were written; ``False`` when there is no
            song, no edits, or the write failed (already reported).
        """
        if self._edits is None or len(self._edits) == 0 or self._session.path is None:
            return False
        document = self._session.document
        provenance = document.provenance if document is not None else None
        try:
            target = save_edits_document(
                self._edits,
                edits_sidecar_path(self._session.path),
                input_path=str(self._session.path),
                input_hash=provenance.input_hash if provenance is not None else None,
            )
        except SongLabError as error:
            self._report(error)
            return False
        status_bar = self.statusBar()
        assert status_bar is not None  # QMainWindow always creates one on demand
        status_bar.showMessage(f"Edits saved to {target.name}", 5000)
        return True

    def _restore_saved_edits(self, path: Path) -> None:
        """Replay the sidecar over the freshly analysed engine layer, if any.

        No sidecar is the normal case and stays silent. A sidecar that no
        longer replays (stale, corrupt, a different version) is reported and
        the pure engine layer is kept - an honest failure, never a silently
        dropped edit and never a broken window.
        """
        sidecar = edits_sidecar_path(path)
        if not sidecar.is_file() or self._edits is None:
            return
        try:
            self._edits = rebuild_stack(load_edits(sidecar))
        except SongLabError as error:
            self._report(error)
            self._edits = CommandStack(self._edits.base)

    # -- the one refresh ---------------------------------------------------

    def refresh(self) -> DisplayFrame | None:
        """Read one snapshot and draw it; returns the frame drawn.

        This is the whole synchronization of the window, and it is the same
        operation the terminal display performs: one snapshot per tick, turned
        into a frame. A test calls it directly with the fake clock advanced,
        which is how "the chord follows the playhead" is asserted without
        sleeping.
        """
        if not self._session.is_open:
            return None
        snapshot = self._session.snapshot()
        frame = frame_from(snapshot)
        # The label reads the *effective* chord layer: what the user edited is
        # what the label shows, in the same clock the snapshot froze.
        if self._edits is not None:
            edited = self._edits.effective_chord_at(frame.position)
            if edited is not None or snapshot.chord is not None:
                frame = replace(frame, chord=edited)
        self._frame = frame
        self._chord_label.setText(frame.chord_text)
        self._time_label.setText(frame.time_text)
        self._state_label.setText(frame.state.value)
        self._play_action.setText("Pause" if frame.state is PlaybackState.PLAYING else "Play")
        self._timeline.set_playhead(frame.position, frame.duration)
        # Same snapshot, same clock: the session answers which line and word
        # sound at this playhead, the widget only draws the answer.
        self._lyrics.set_active(
            self._session.lyric_at(frame.position),
            self._session.word_at(frame.position),
        )
        return frame

    def _report(self, error: SongLabError) -> None:
        """Show an expected failure the way the CLI prints it."""
        text = error.message
        if error.hint:
            text = f"{text}\n\n{error.hint}"
        QMessageBox.warning(self, "Song Chord Lyrics Analyzer", text)

    def closeEvent(self, event: QCloseEvent | None) -> None:
        """Stop the refresh timer and release the audio device."""
        self._timer.stop()
        self._session.close()
        super().closeEvent(event)


def launch(
    audio: str | Path | None = None,
    *,
    engines: Mapping[str, str] | None = None,
    input_hash: bool = True,
    argv: list[str] | None = None,
) -> int:
    """Open the window and run the Qt event loop.

    Args:
        audio: Optional file to open straight away.
        engines: Optional ``kind -> engine name`` overrides for the analysis.
        input_hash: Whether opening a file records its SHA-256 in provenance.
        argv: Arguments passed on to ``QApplication``.

    Returns:
        The exit code of the event loop, or ``1`` when ``audio`` was given and
        could not be opened (the reason is shown in a dialog first).
    """
    existing = QApplication.instance()
    app = (
        existing
        if isinstance(existing, QApplication)
        else QApplication(list(argv) if argv is not None else sys.argv[:1])
    )
    window = MainWindow(engines=engines, input_hash=input_hash)
    window.show()
    if audio is not None and not window.open_file(audio):
        window.close()
        return 1
    return int(app.exec())
