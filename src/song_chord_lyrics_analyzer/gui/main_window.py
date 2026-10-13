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
from PyQt6.QtGui import QAction, QCloseEvent, QCursor, QKeySequence, QResizeEvent
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
    lyric_at,
    summarize,
    word_at,
)
from song_chord_lyrics_analyzer.app.editing import (
    CommandStack,
    DeleteChord,
    DeleteLyric,
    EditCommand,
    InsertChord,
    InsertLyric,
    MergeChords,
    SetChordLabel,
    SetLyricText,
    SetLyricTiming,
    SimplifyChords,
    SplitChord,
    TransposeChords,
    TrimChord,
)
from song_chord_lyrics_analyzer.app.persistence import (
    edits_sidecar_path,
    load_edits,
    rebuild_stack,
)
from song_chord_lyrics_analyzer.app.persistence import (
    save_edits as save_edits_document,
)
from song_chord_lyrics_analyzer.audio.playback import PlaybackState
from song_chord_lyrics_analyzer.export import export_document
from song_chord_lyrics_analyzer.gui.analysis_panel import AnalysisPanel
from song_chord_lyrics_analyzer.gui.lyrics_view import LyricsWidget
from song_chord_lyrics_analyzer.gui.timeline import TimelineWidget
from song_chord_lyrics_analyzer.utils.errors import SongLabError

__all__ = ["AUDIO_FILTER", "AUDIO_SUFFIXES", "EXPORT_FILTER", "MainWindow", "launch"]

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

#: The save dialog's format choice, the same formats ``songlab export`` takes.
#: The order and wording is what the user sees; the mapping below turns the
#: chosen filter into the :data:`~song_chord_lyrics_analyzer.export.EXPORT_FORMATS`
#: name - nothing here renders anything itself.
EXPORT_FILTER = "ChordPro (*.pro *.crd);;Markdown (*.md);;JSON (*.json)"

_EXPORT_FORMAT_BY_FILTER = {
    "ChordPro (*.pro *.crd)": "chordpro",
    "Markdown (*.md)": "markdown",
    "JSON (*.json)": "json",
}

_SAVING_SUFFIX_FORMATS = {
    ".pro": "chordpro",
    ".crd": "chordpro",
    ".md": "markdown",
    ".json": "json",
}

#: Seek step of the back/forward actions, in seconds.
SEEK_STEP = 5.0


def _format_for(selected: str, target: Path) -> str:
    """The ``songlab export`` format name for the dialog's choice.

    Qt's rule stands: the picked filter is authoritative, and it maps onto
    :data:`EXPORT_FORMATS` through ``_EXPORT_FORMAT_BY_FILTER``. The typed
    name's suffix decides only when the dialog reports no filter of ours (an
    empty string comes back from cancelled or tool-less calls), and anything
    else exports as ChordPro - the format ``songlab export`` defaults to.
    Nothing here renders anything.
    """
    by_filter = _EXPORT_FORMAT_BY_FILTER.get(selected)
    if by_filter is not None:
        return by_filter
    return _SAVING_SUFFIX_FORMATS.get(target.suffix.lower(), "chordpro")


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
        #: What was last written to (or restored from) the sidecar, for the
        #: close prompt: the tape equals this exactly when nothing is unsaved.
        self._saved_applied: tuple[EditCommand, ...] = ()

        self.setWindowTitle("Song Chord Lyrics Analyzer")
        self.resize(960, 560)
        self._build_actions()
        self._build_widgets()
        # The actions start honest: nothing to undo/redo/save, no song to
        # export, before the first open.
        self._update_edit_actions()

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

        # Phase H: the whole-document transforms ride the same tape as the
        # per-chord edits - one Ctrl+Z takes a transpose back like any other
        # edit, and Ctrl+S persists it to the sidecar.
        self._transpose_action = QAction("Transpose chords...", self)
        self._transpose_action.triggered.connect(self.transpose_chords)

        self._simplify_action = QAction("Simplify chords", self)
        self._simplify_action.triggered.connect(self.simplify_chords)

        # Phase H: the same exporters `songlab export` uses, offered from the
        # window - the dialog only picks a file and a format, the write goes
        # through the identical seam so the two surfaces cannot drift.
        self._export_action = QAction("Export document...", self)
        self._export_action.setShortcut(QKeySequence("Ctrl+Shift+E"))
        self._export_action.triggered.connect(self.export_file_dialog)

        toolbar = self.addToolBar("Transport")
        assert toolbar is not None  # always created by QMainWindow
        toolbar.setMovable(False)
        for action in (
            self._open_action,
            self._save_action,
            self._export_action,
            self._play_action,
            self._stop_action,
            self._back_action,
            self._forward_action,
        ):
            toolbar.addAction(action)

        edit_menu = self.addToolBar("Edit")
        assert edit_menu is not None
        edit_menu.setMovable(False)
        edit_menu.addAction(self._transpose_action)
        edit_menu.addAction(self._simplify_action)

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
        self._lyrics.line_menu_requested.connect(self._show_lyric_menu)
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
            self._edits = CommandStack(
                document.chords if document is not None else [],
                lyrics=document.lyrics if document is not None else [],
            )
            self._restore_saved_edits(Path(path))
            # Restored commands came from disk: they count as saved.
            assert self._edits is not None
            self._saved_applied = self._edits.applied
            self._populate_timeline()
            self._populate_lyrics()
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

    def _populate_lyrics(self) -> None:
        """Draw the *effective* lyric layer (engine + the user's edits).

        Same rule as the chord strip: the view shows what the tape produced,
        never the document's raw list, so a lyric edit is on screen the moment
        its command is pushed.
        """
        lines = self._edits.effective_lyrics if self._edits is not None else []
        self._lyrics.set_document(lines)

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
        self._after_edit()
        return True

    def edit_menu_entries(self, position: float) -> tuple[tuple[str, str, bool], ...]:
        """The timeline's context menu as ``(label, choice, enabled)`` rows.

        One row per Phase G command, each addressed by the chord under
        ``position`` (or by the gap, for insert). Tests read this tuple to
        assert the enable states a user would see, without ever opening a menu.
        """
        if self._edits is None:
            return ()
        event = self._edits.effective_chord_at(position)
        inside = event is not None and position > event.start
        ends_before_click = event is not None and event.end is not None and position < event.end
        split_ok = inside and (event is not None and (event.end is None or position < event.end))
        trim_start_ok = inside and ends_before_click  # an open end cannot be trimmed from the start
        trim_end_ok = inside and (event is not None and (event.end is None or position < event.end))
        merge_ok = event is not None and any(
            one.start > event.start for one in self._edits.effective
        )
        return (
            ("Edit chord here...", "edit", event is not None),
            ("Split here", "split", split_ok),
            ("Trim start to here", "trim-start", trim_start_ok),
            ("Trim end to here", "trim-end", trim_end_ok),
            ("Merge with next chord", "merge-next", merge_ok),
            ("Delete chord", "delete", event is not None),
            ("Insert chord here...", "insert", event is None),
        )

    def apply_edit_choice(self, choice: str, position: float) -> bool:
        """Perform one context-menu command at ``position``; ``False`` if none.

        "edit" opens the label dialog; the others push their command straight
        away ("insert" asks for the label first). A rejected command is
        reported like every other edit failure and leaves the tape untouched.

        Args:
            choice: One of the choice keys in :meth:`edit_menu_entries`.
            position: The clicked time in seconds.

        Returns:
            ``True`` when an edit was applied (or the dialog accepted).
        """
        if self._edits is None:
            return False
        if choice == "edit":
            return self.edit_chord_at(position)
        event = self._edits.effective_chord_at(position)
        try:
            if choice == "split" and event is not None:
                command: EditCommand = SplitChord(event.start, position)
            elif choice == "trim-start" and event is not None:
                command = TrimChord(event.start, new_start=position)
            elif choice == "trim-end" and event is not None:
                command = TrimChord(event.start, new_end=position)
            elif choice == "merge-next" and event is not None:
                following = next(
                    (one for one in self._edits.effective if one.start > event.start),
                    None,
                )
                if following is None:
                    return False
                command = MergeChords(event.start, following.start)
            elif choice == "delete" and event is not None:
                command = DeleteChord(event.start)
            elif choice == "insert":
                label, accepted = QInputDialog.getText(
                    self,
                    "Insert chord",
                    f"Chord label from {position:.2f} s (open-ended):",
                )
                if not accepted:
                    return False
                command = InsertChord(position, label)
            else:
                return False
        except SongLabError as error:
            self._report(error)
            return False
        try:
            self._edits.push(command)
        except SongLabError as error:
            self._report(error)
            return False
        self._after_edit()
        return True

    def _show_edit_menu(self, pos: QPoint) -> None:
        """The timeline's context menu: the chord commands, undo, redo."""
        if self._edits is None:
            return
        position = self._timeline.seconds_at(pos.x())
        menu = QMenu(self)
        choices: dict[QAction, str] = {}
        for label, key, enabled in self.edit_menu_entries(position):
            action = menu.addAction(label)
            if action is not None:
                action.setEnabled(enabled)
                choices[action] = key
        menu.addSeparator()
        for label, key, enabled in self.transform_menu_entries():
            action = menu.addAction(label)
            if action is not None:
                action.setEnabled(enabled)
                choices[action] = key
        menu.addSeparator()
        assert self._undo_action is not None and self._redo_action is not None
        menu.addAction(self._undo_action)
        menu.addAction(self._redo_action)
        chosen = menu.exec(self._timeline.mapToGlobal(pos))
        if chosen is not None:
            picked = choices.get(chosen)
            if picked is not None:
                if picked in ("transpose", "simplify"):
                    self.apply_transform_choice(picked)
                else:
                    self.apply_edit_choice(picked, position)
        if chosen is not None:
            picked = choices.get(chosen)
            if picked is not None:
                self.apply_edit_choice(picked, position)

    # -- document-level transforms (Phase H) -------------------------------

    def transform_menu_entries(self) -> tuple[tuple[str, str, bool], ...]:
        """The whole-document chords transforms as ``(label, choice, enabled)``.

        One row per Phase H transform; both act on the entire effective chord
        layer, so both are enabled whenever a song is open - even on an empty
        layer, where a transpose is a no-op worth allowing (it still lands on
        the tape and costs one Ctrl+Z to take back). Tests read this tuple to
        assert what a user would see, without ever opening a menu.
        """
        if self._edits is None:
            return ()
        return (
            ("Transpose all chords...", "transpose", True),
            ("Simplify all chords", "simplify", True),
        )

    def apply_transform_choice(self, choice: str) -> bool:
        """Perform one whole-document chord transform; ``False`` if unknown.

        "transpose" asks for the semitone offset (-11..+11) first (a cancelled
        dialog changes nothing); "simplify" pushes straight away. The commands
        go on the same tape as the per-chord edits, so undo/redo and Ctrl+S
        cover them with nothing new to wire.

        Args:
            choice: ``"transpose"`` or ``"simplify"``.

        Returns:
            ``True`` when a transform was applied (or the dialog accepted).
        """
        if self._edits is None:
            return False
        if choice == "transpose":
            return self.transpose_chords()
        if choice == "simplify":
            return self._push_transform(SimplifyChords())
        return False

    def _push_transform(self, command: EditCommand) -> bool:
        """Push one transform command onto the tape and redraw; report failures."""
        try:
            self._edits.push(command)  # type: ignore[union-attr]
        except SongLabError as error:
            self._report(error)
            return False
        self._after_edit()
        return True

    def transpose_chords(self) -> bool:
        """The Transpose action: ask for the semitones, push the command."""
        semitones, accepted = QInputDialog.getInt(
            self,
            "Transpose chords",
            "Semitones to transpose every chord by (-11..+11):",
            value=0,
            min=-11,
            max=11,
        )
        if not accepted:
            return False
        return self.apply_transform_choice_with_semitones(semitones)

    def apply_transform_choice_with_semitones(self, semitones: int | None) -> bool:
        """The transpose path with the dialog pre-answered (or cancelled).

        The same validation and reporting as the interactive transpose - the
        dialog result is simply given instead of asked, which is what lets a
        headless test drive the real code path.
        """
        if semitones is None:  # a cancelled dialog
            return False
        try:
            command = TransposeChords(semitones)
        except SongLabError as error:  # an offset the command itself rejects
            self._report(error)
            return False
        return self._push_transform(command)

    def simplify_chords(self) -> bool:
        """The Simplify action: push the command straight away."""
        return self.apply_transform_choice("simplify")

    # -- lyric editing (Phase G) -------------------------------------------

    def lyric_menu_entries(self, index: int) -> tuple[tuple[str, str, bool], ...]:
        """The lyrics view's context menu as ``(label, choice, enabled)`` rows.

        One row per lyric command, addressed by the display index of the line
        under the click - the same index the commands resolve against. "Set
        end" is off until the line has a start to end against, the order the
        commands themselves enforce. Tests read this tuple to assert the
        enable states a user would see, without ever opening a menu.
        """
        if self._edits is None:
            return ()
        lines = self._edits.effective_lyrics
        if not 0 <= index < len(lines):
            return ()
        line = lines[index]
        return (
            ("Edit text...", "text", True),
            ("Set start...", "set-start", True),
            ("Set end...", "set-end", line.start is not None),
            ("Insert line...", "insert", True),
            ("Delete line", "delete", True),
        )

    def apply_lyric_choice(self, choice: str, index: int) -> bool:
        """Perform one lyrics-menu command on line ``index``; ``False`` if none.

        "text", "set-start" and "set-end" ask for the value first (a cancelled
        dialog changes nothing); "insert" appends a line the user can then
        time; "delete" pushes straight away. A rejected command is reported
        like every other edit failure and leaves the tape untouched.

        Args:
            choice: One of the choice keys in :meth:`lyric_menu_entries`.
            index: The display index of the line under the click.

        Returns:
            ``True`` when an edit was applied (or the dialog accepted).
        """
        if self._edits is None:
            return False
        lines = self._edits.effective_lyrics
        if not 0 <= index < len(lines):
            return False
        line = lines[index]
        try:
            if choice == "text":
                text, accepted = QInputDialog.getText(
                    self,
                    "Edit lyric line",
                    f"Line {index + 1} of {len(lines)}:",
                    text=line.text,
                )
                if not accepted:
                    return False
                command: EditCommand = SetLyricText(index, text)
            elif choice == "set-start":
                value, accepted = QInputDialog.getDouble(
                    self,
                    "Set line start",
                    "Start (seconds):",
                    value=0.0 if line.start is None else line.start,
                    min=0.0,
                    max=1e9,
                    decimals=3,
                )
                if not accepted:
                    return False
                command = SetLyricTiming(index, new_start=value)
            elif choice == "set-end" and line.start is not None:
                value, accepted = QInputDialog.getDouble(
                    self,
                    "Set line end",
                    "End (seconds):",
                    value=(line.start + 1.0) if line.end is None else line.end,
                    min=0.0,
                    max=1e9,
                    decimals=3,
                )
                if not accepted:
                    return False
                command = SetLyricTiming(index, new_end=value)
            elif choice == "insert":
                text, accepted = QInputDialog.getText(self, "Insert lyric line", "Line text:")
                if not accepted:
                    return False
                command = InsertLyric(text)
            elif choice == "delete":
                command = DeleteLyric(index)
            else:
                return False
        except SongLabError as error:
            self._report(error)
            return False
        try:
            self._edits.push(command)
        except SongLabError as error:
            self._report(error)
            return False
        self._after_edit()
        return True

    def _show_lyric_menu(self, index: int) -> None:
        """The lyrics view's context menu: the line commands, undo, redo.

        The index arrives from the widget (the line under the pointer) and the
        menu opens where the pointer is - which for a context menu is where
        the user is already looking.
        """
        if self._edits is None:
            return
        menu = QMenu(self)
        choices: dict[QAction, str] = {}
        for label, key, enabled in self.lyric_menu_entries(index):
            action = menu.addAction(label)
            if action is not None:
                action.setEnabled(enabled)
                choices[action] = key
        menu.addSeparator()
        assert self._undo_action is not None and self._redo_action is not None
        menu.addAction(self._undo_action)
        menu.addAction(self._redo_action)
        chosen = menu.exec(QCursor.pos())
        if chosen is not None:
            picked = choices.get(chosen)
            if picked is not None:
                self.apply_lyric_choice(picked, index)

    def undo_edit(self) -> bool:
        """Take the last edit back; ``False`` when there is nothing to undo."""
        if self._edits is None or self._edits.undo() is None:
            return False
        self._after_edit()
        return True

    def redo_edit(self) -> bool:
        """Reapply the last undone edit; ``False`` when there is nothing to redo."""
        if self._edits is None or self._edits.redo() is None:
            return False
        self._after_edit()
        return True

    def _after_edit(self) -> None:
        """Redraw both layers and the edit actions after any tape change.

        Chord and lyric commands share one tape, so undo/redo may have moved
        either layer - both are repopulated unconditionally rather than
        guessing which one moved.
        """
        self._populate_timeline()
        self._populate_lyrics()
        self._update_edit_actions()
        self.refresh()

    def _update_edit_actions(self) -> None:
        """Enable Undo/Redo/Save only when the tape can serve them."""
        undo, redo, save = self._undo_action, self._redo_action, self._save_action
        assert undo is not None and redo is not None and save is not None
        undo.setEnabled(self._edits is not None and self._edits.can_undo)
        redo.setEnabled(self._edits is not None and self._edits.can_redo)
        save.setEnabled(self._edits is not None and len(self._edits) > 0)
        export = self._export_action
        assert export is not None
        export.setEnabled(self._session.is_open)

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
        assert self._edits is not None  # guarded above
        self._saved_applied = self._edits.applied
        return True

    # -- export (Phase H) ---------------------------------------------------

    def export_file_dialog(self) -> bool:
        """Ask for a file and format, then export the open song.

        The save dialog proposes a sibling file named after the song and lets
        the user choose one of the :data:`EXPORT_FORMATS` through its filter. A
        cancelled dialog changes nothing. ``False`` when there is no open song
        either way - the action is disabled before then.
        """
        path = self._session.path
        if path is None or not self._session.is_open:
            return False
        proposed = path.with_suffix(".chordpro")
        chosen, selected = QFileDialog.getSaveFileName(
            self,
            "Export document",
            str(proposed),
            EXPORT_FILTER,
        )
        if not chosen:
            return False
        return self.export_document_to(Path(chosen), _format_for(selected, Path(chosen)))

    def export_document_to(self, target: Path, fmt: str) -> bool:
        """Write the open song's effective layers to ``target`` as ``fmt``.

        The dialog pre-answered: the same exporter ``songlab export`` calls,
        fed the *effective* chord and lyric layers (edits included) - what is
        exported is what the window shows, not the raw engine output.

        Returns:
            ``True`` when the file was written; ``False`` when there is no song
            or the write failed (already reported).
        """
        document = self._session.document
        if document is None or not self._session.is_open:
            return False
        chords = self._edits.effective if self._edits is not None else None
        lyrics = self._edits.effective_lyrics if self._edits is not None else None
        try:
            written = export_document(document, fmt, target, chords=chords, lyrics=lyrics)
        except SongLabError as error:
            self._report(error)
            return False
        except OSError as error:
            self._report(
                SongLabError(
                    f"Could not write {target}: {error}",
                    hint="Choose a location this user can write to.",
                )
            )
            return False
        status_bar = self.statusBar()
        assert status_bar is not None  # QMainWindow always creates one on demand
        status_bar.showMessage(f"Exported {fmt} to {written.name}", 5000)
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
            self._edits = CommandStack(self._edits.base, lyrics=self._edits.base_lyrics)

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
        # Same snapshot, same clock - and the *effective* lyric layer, like the
        # chord label: after an edit the view shows what the user made, and the
        # same presenters the session uses answer which line and word sound now.
        lines = self._edits.effective_lyrics if self._edits is not None else self._session.lyrics
        segment = lyric_at(lines, frame.position)
        self._lyrics.set_active(segment, word_at(segment, frame.position))
        return frame

    def _report(self, error: SongLabError) -> None:
        """Show an expected failure the way the CLI prints it."""
        text = error.message
        if error.hint:
            text = f"{text}\n\n{error.hint}"
        QMessageBox.warning(self, "Song Chord Lyrics Analyzer", text)

    def closeEvent(self, event: QCloseEvent | None) -> None:
        """Offer to save unsaved edits, stop the timer, release the device.

        "Unsaved" means the tape differs from what was last written or
        restored, so undoing back to the saved state closes silently - the
        answer is exact, not a dirty flag that lies.
        """
        if self._unsaved_edits() and not self._confirm_close():
            if event is not None:
                event.ignore()
            return
        self._timer.stop()
        self._session.close()
        super().closeEvent(event)

    def _unsaved_edits(self) -> bool:
        """Whether the tape differs from the last save/restore.

        Commands are frozen dataclasses, so tuple equality is exact: undoing
        back to the saved state counts as saved, and a redo counts as unsaved.
        """
        if self._edits is None:
            return False
        return self._edits.applied != self._saved_applied

    def _confirm_close(self) -> bool:
        """Ask what to do about unsaved edits; ``True`` closes the window."""
        answer = QMessageBox.question(
            self,
            "Unsaved chord edits",
            "The chord edits have not been saved. Save them before closing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.save_edits_sidecar()
        return answer == QMessageBox.StandardButton.Discard


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
