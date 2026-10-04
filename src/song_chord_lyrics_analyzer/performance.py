"""Performance measurement (roadmap section 45).

An engine run wrapped in :func:`measure_performance` — or bracketed by
``PerformanceProbe.start()`` / ``PerformanceProbe.stop()`` — produces a
:class:`PerformanceReport` with the numbers the roadmap asks for:
processing time, seconds of audio per second of computation (the
real-time factor), peak RAM, startup time (imports and model loading),
model size, disk usage and the device the run used.

Honesty rules (roadmap section 43):

* every number is measured at run time on this machine — nothing is copied
  from a vendor table or estimated;
* a value the platform cannot report stays ``None``: Windows has no
  :mod:`resource` module, so ``peak_rss_bytes`` is ``None`` there instead of
  a guess;
* VRAM stays ``None`` on CPU runs. ``vram_bytes`` is only ever filled by a
  caller that actually measured it;
* the real-time factor is reported only when both the audio duration and the
  processing time are known and positive.

Everything here is standard library — the core package has zero required
dependencies.
"""

from __future__ import annotations

import math
import shutil
import sys
import time
import tracemalloc
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:  # pragma: no cover - exercised implicitly by the platform
    import resource as _resource
except ImportError:  # Windows: no getrusage, so no peak-RSS figure
    _resource = None  # type: ignore[assignment]

__all__ = [
    "PerformanceProbe",
    "PerformanceReport",
    "free_disk_bytes",
    "measure_performance",
    "model_size_bytes",
    "peak_rss_bytes",
    "real_time_factor",
]


def real_time_factor(
    audio_seconds: float | None,
    processing_time_seconds: float | None,
) -> float | None:
    """Seconds of audio per second of computation, or ``None`` when unknowable.

    A value above ``1.0`` means the run finished faster than real time. The
    ratio is only reported when both inputs are finite and positive; anything
    else would be a guess rather than a measurement.
    """
    if audio_seconds is None or processing_time_seconds is None:
        return None
    audio = float(audio_seconds)
    processing = float(processing_time_seconds)
    if not math.isfinite(audio) or not math.isfinite(processing):
        return None
    if audio <= 0.0 or processing <= 0.0:
        return None
    return audio / processing


def peak_rss_bytes() -> int | None:
    """Peak resident set size of this process in bytes, when the OS reports it.

    ``ru_maxrss`` is reported in KiB on Linux and in bytes on macOS. Windows
    has no :mod:`resource` module, so ``None`` is returned — an unavailable
    number is never replaced by an estimate.
    """
    if _resource is None:  # pragma: no cover - Windows only
        return None
    raw = _resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return int(raw)
    return int(raw) * 1024


def model_size_bytes(path: Path | str) -> int | None:
    """Size in bytes of a model file, or of every file inside a model directory.

    Returns ``None`` when the path does not exist, so a missing model reads as
    "not measured" instead of zero bytes.
    """
    target = Path(path)
    try:
        if target.is_file():
            return target.stat().st_size
        if target.is_dir():
            return sum(item.stat().st_size for item in target.rglob("*") if item.is_file())
    except OSError:
        return None
    return None


def free_disk_bytes(path: Path | str) -> int | None:
    """Free bytes on the filesystem holding ``path`` (disk budget for downloads)."""
    try:
        return int(shutil.disk_usage(Path(path)).free)
    except OSError:
        return None


@dataclass(frozen=True)
class PerformanceReport:
    """The section 45 numbers of one measured run.

    Attributes:
        processing_time_seconds: Wall-clock time of the measured block.
        audio_seconds: Duration of the audio the block processed, when known.
        real_time_factor: ``audio_seconds / processing_time_seconds``, when
            both are known and positive.
        startup_time_seconds: Time spent importing dependencies or loading
            models before the measured block, when the caller measured it.
        peak_rss_bytes: Peak resident set size of the process, when the OS
            reports it.
        peak_python_bytes: Peak Python heap while ``tracemalloc`` traced the
            block, when tracing was requested.
        model_size_bytes: Size of the engine's model files, when there are any.
        disk_free_bytes: Free space on the target filesystem, when measured.
        device: Device class the run used (``"cpu"`` today; a GPU engine would
            report ``"gpu"``).
        vram_bytes: Peak VRAM, only when a caller actually measured it. CPU
            runs report ``None`` — no number is invented.
    """

    processing_time_seconds: float
    audio_seconds: float | None = None
    real_time_factor: float | None = None
    startup_time_seconds: float | None = None
    peak_rss_bytes: int | None = None
    peak_python_bytes: int | None = None
    model_size_bytes: int | None = None
    disk_free_bytes: int | None = None
    device: str = "cpu"
    vram_bytes: int | None = None

    def as_dict(self) -> dict[str, Any]:
        """The report as a plain JSON-serializable dictionary."""
        return asdict(self)


class PerformanceProbe:
    """Measures one block of work (create it, call :meth:`start`, then :meth:`stop`).

    ``audio_seconds`` is a public attribute on purpose: the audio duration is
    often only known *after* loading the file, so it can be set right before
    :meth:`stop` computes the real-time factor. ``stop`` returns the report and
    also stores it in :attr:`report`.
    """

    def __init__(
        self,
        *,
        audio_seconds: float | None = None,
        startup_time_seconds: float | None = None,
        model_path: Path | str | None = None,
        disk_path: Path | str | None = None,
        device: str = "cpu",
        vram_bytes: int | None = None,
        trace_python: bool = False,
    ) -> None:
        self.audio_seconds = audio_seconds
        self.startup_time_seconds = startup_time_seconds
        self.model_path = Path(model_path) if model_path is not None else None
        self.disk_path = Path(disk_path) if disk_path is not None else None
        self.device = device
        self.vram_bytes = vram_bytes
        self.trace_python = trace_python
        self.report: PerformanceReport | None = None
        self._started_at: float | None = None
        self._owns_tracing = False

    def start(self) -> None:
        """Begin measuring (wall clock and, on request, Python allocations)."""
        if self._started_at is not None:
            raise RuntimeError("PerformanceProbe.start() called twice")
        self._started_at = time.perf_counter()
        if self.trace_python:
            if not tracemalloc.is_tracing():
                tracemalloc.start()
                self._owns_tracing = True
            tracemalloc.reset_peak()

    def stop(self) -> PerformanceReport:
        """Stop measuring and return the :class:`PerformanceReport`.

        Raises:
            RuntimeError: When :meth:`start` was never called.
        """
        if self._started_at is None:
            raise RuntimeError("PerformanceProbe.stop() called before start()")
        processing = time.perf_counter() - self._started_at
        self._started_at = None

        peak_python: int | None = None
        if self.trace_python and tracemalloc.is_tracing():
            peak_python = tracemalloc.get_traced_memory()[1]
        if self._owns_tracing:
            tracemalloc.stop()
            self._owns_tracing = False

        report = PerformanceReport(
            processing_time_seconds=processing,
            audio_seconds=self.audio_seconds,
            real_time_factor=real_time_factor(self.audio_seconds, processing),
            startup_time_seconds=self.startup_time_seconds,
            peak_rss_bytes=peak_rss_bytes(),
            peak_python_bytes=peak_python,
            model_size_bytes=(
                model_size_bytes(self.model_path) if self.model_path is not None else None
            ),
            disk_free_bytes=free_disk_bytes(self.disk_path) if self.disk_path is not None else None,
            device=self.device,
            vram_bytes=self.vram_bytes,
        )
        self.report = report
        return report

    def __enter__(self) -> PerformanceProbe:
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        if self._started_at is not None:
            self.stop()


@contextmanager
def measure_performance(
    *,
    audio_seconds: float | None = None,
    startup_time_seconds: float | None = None,
    model_path: Path | str | None = None,
    disk_path: Path | str | None = None,
    device: str = "cpu",
    vram_bytes: int | None = None,
    trace_python: bool = False,
) -> Iterator[PerformanceProbe]:
    """Measure the ``with`` block and expose the result as ``probe.report``.

    Example::

        with measure_performance(audio_seconds=180.0) as probe:
            labels = engine.decode(chroma)
        print(probe.report.real_time_factor)
    """
    probe = PerformanceProbe(
        audio_seconds=audio_seconds,
        startup_time_seconds=startup_time_seconds,
        model_path=model_path,
        disk_path=disk_path,
        device=device,
        vram_bytes=vram_bytes,
        trace_python=trace_python,
    )
    probe.start()
    try:
        yield probe
    finally:
        if probe._started_at is not None:
            probe.stop()
