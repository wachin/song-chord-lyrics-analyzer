"""Opening a song off the UI thread (roadmap Phase K).

Opening a file decodes it and runs four engines over it. On a long recording
that is minutes of work, and doing it on the UI thread froze the window for
exactly that long - the one user-visible cost the long-song work made reachable
on purpose. The seam is :class:`AnalysisRunner`: the window submits work and is
answered through callbacks, never through a return value that only exists once
the work is done.

Two implementations, one contract:

* :class:`ThreadedAnalysis` (the default, and what ``songlab gui`` uses) runs the
  work on a :class:`QThread`. The session is not thread-safe and neither are Qt
  widgets, so the worker touches the session only and reports through signals;
  Qt delivers them to the window's slots on the GUI thread because the objects
  live in different threads.
* :class:`ImmediateAnalysis` runs the work on the calling thread with the same
  callbacks in the same order. Tests use it to assert the post-analysis state
  the moment ``open_file()`` returns, and the threading is then tested on its
  own - with an analysis the test can hold open - instead of being smeared over
  every widget test.

Nothing here is analysis logic: the work *is* the session's own ``open()``, the
progress events come from the service (Phase K), and a failure is forwarded to
the caller, never swallowed and never turned into a half-open session.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol, runtime_checkable

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from song_chord_lyrics_analyzer.analysis import ProgressEvent
from song_chord_lyrics_analyzer.app import SongSession
from song_chord_lyrics_analyzer.models.analysis import AnalysisResult

__all__ = [
    "SHUTDOWN_WAIT_MS",
    "AnalysisJob",
    "AnalysisRunner",
    "ImmediateAnalysis",
    "ThreadedAnalysis",
]

#: How long a teardown waits for a running analysis, in milliseconds. The wait
#: only ever happens after the engine call has already returned, so it is a
#: join, not a timeout: the number is a guard, not a budget.
SHUTDOWN_WAIT_MS = 30_000

#: The callbacks every runner accepts. They run on the caller's thread, in this
#: order, and never both ``on_done`` and ``on_failed``.
ProgressCallback = Callable[[ProgressEvent], None]
DoneCallback = Callable[[AnalysisResult], None]
FailedCallback = Callable[[BaseException], None]


@runtime_checkable
class AnalysisRunner(Protocol):
    """How the window starts an analysis without blocking its own thread."""

    @property
    def is_running(self) -> bool:
        """Whether an analysis is under way."""
        ...

    def submit(
        self,
        path: str | Path,
        *,
        engines: Mapping[str, str] | None = None,
        input_hash: bool = True,
        on_progress: ProgressCallback | None = None,
        on_done: DoneCallback | None = None,
        on_failed: FailedCallback | None = None,
    ) -> bool:
        """Start analysing ``path``.

        Returns:
            ``True`` when the work is under way - or, for a synchronous runner,
            when it finished successfully; ``False`` when it could not start
            (another analysis is running) or, synchronously, when it failed and
            ``on_failed`` was already called.
        """
        ...

    def wait(self, timeout_ms: int = SHUTDOWN_WAIT_MS) -> bool:
        """Block until a running analysis ends; ``True`` when nothing is left."""
        ...


class AnalysisJob(QObject):
    """One ``session.open()`` on a worker thread, reported through signals.

    The object is moved to the worker thread before it runs, so its signals are
    delivered to the window's slots as queued calls - the window's callbacks
    run on the GUI thread, where touching widgets is legal.
    """

    progress = pyqtSignal(object)
    done = pyqtSignal(object)
    failed = pyqtSignal(object)

    def __init__(
        self,
        session: SongSession,
        path: str | Path,
        *,
        engines: Mapping[str, str] | None = None,
        input_hash: bool = True,
    ) -> None:
        super().__init__()
        self._session = session
        self._path = Path(path)
        self._engines = dict(engines) if engines else None
        self._input_hash = input_hash

    @pyqtSlot()
    def run(self) -> None:
        """Open the song; report the document or the failure, never both."""
        try:
            document = self._session.open(
                self._path,
                engines=self._engines,
                input_hash=self._input_hash,
                on_progress=self.progress.emit,
            )
        except Exception as error:  # forwarded to the window, never swallowed
            self.failed.emit(error)
            return
        self.done.emit(document)


class ThreadedAnalysis(QObject):
    """Runs one analysis at a time on a worker thread (the default runner).

    Args:
        session: The session the work opens the song in. The runner owns the
            thread it touches that session from, so the GUI must not call into
            the session while :attr:`is_running` is true.
        parent: Qt parent, for embedding.
    """

    def __init__(self, session: SongSession, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._session = session
        self._thread: QThread | None = None
        self._job: AnalysisJob | None = None

    @property
    def is_running(self) -> bool:
        """Whether the worker thread is still analysing."""
        return self._thread is not None

    def submit(
        self,
        path: str | Path,
        *,
        engines: Mapping[str, str] | None = None,
        input_hash: bool = True,
        on_progress: ProgressCallback | None = None,
        on_done: DoneCallback | None = None,
        on_failed: FailedCallback | None = None,
    ) -> bool:
        """Start the analysis; ``False`` when one is already running."""
        if self.is_running:
            return False
        thread = QThread()
        job = AnalysisJob(self._session, path, engines=engines, input_hash=input_hash)
        job.moveToThread(thread)
        thread.started.connect(job.run)
        # Teardown is connected before the caller's callbacks, so the thread is
        # already joined when they run - a callback may start the next analysis.
        job.done.connect(self._finish)
        job.failed.connect(self._finish)
        thread.finished.connect(job.deleteLater)
        thread.finished.connect(thread.deleteLater)
        if on_progress is not None:
            job.progress.connect(on_progress)
        if on_done is not None:
            job.done.connect(on_done)
        if on_failed is not None:
            job.failed.connect(on_failed)
        self._thread = thread
        self._job = job
        thread.start()
        return True

    def wait(self, timeout_ms: int = SHUTDOWN_WAIT_MS) -> bool:
        """Block until the analysis ends; ``True`` when nothing is left."""
        thread = self._thread
        if thread is None:
            return True
        return bool(thread.wait(timeout_ms))

    @pyqtSlot(object)
    def _finish(self, _payload: object) -> None:
        """Join the worker thread once its run has returned."""
        thread = self._thread
        self._thread = None
        self._job = None
        if thread is None:
            return
        thread.quit()
        thread.wait(SHUTDOWN_WAIT_MS)


class ImmediateAnalysis:
    """Runs the analysis on the calling thread, with the same callbacks.

    This is what a test (or an embedder happy to block) uses: the analysis has
    finished when :meth:`submit` returns, so ``MainWindow.open_file()`` answers
    exactly as it did before the work moved off the UI thread.
    """

    def __init__(self, session: SongSession) -> None:
        self._session = session

    @property
    def is_running(self) -> bool:
        """Always ``False``: the work never outlives the call."""
        return False

    def submit(
        self,
        path: str | Path,
        *,
        engines: Mapping[str, str] | None = None,
        input_hash: bool = True,
        on_progress: ProgressCallback | None = None,
        on_done: DoneCallback | None = None,
        on_failed: FailedCallback | None = None,
    ) -> bool:
        """Analyse ``path`` now; ``False`` when the failure was reported."""
        try:
            document = self._session.open(
                path,
                engines=dict(engines) if engines else None,
                input_hash=input_hash,
                on_progress=on_progress,
            )
        except Exception as error:  # reported to the caller, never swallowed
            if on_failed is not None:
                on_failed(error)
            return False
        if on_done is not None:
            on_done(document)
        return True

    def wait(self, timeout_ms: int = SHUTDOWN_WAIT_MS) -> bool:
        """Always ``True``: a synchronous runner has nothing to wait for."""
        return True
