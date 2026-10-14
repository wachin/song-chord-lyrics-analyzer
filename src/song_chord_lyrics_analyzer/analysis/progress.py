"""Progress reporting for one analysis run (roadmap Phase K).

A long analysis used to be a black box: the command printed nothing until every
engine had finished. The service now emits a :class:`ProgressEvent` when it
starts a step and, for a windowed run, once per window - the unit of work that
can actually take minutes. Nothing here measures anything; the events describe
work, the numbers stay the engines' own section 45 measurements.

Two rules keep the events honest:

* **A front end never computes the text.** ``detail`` is filled by the service
  ("window 2 of 14"), because only it knows what a unit of work is; a caller
  that prints a line prints ``detail`` and falls back to the engine name.
* **A callback is never swallowed.** An event is emitted on the caller's stack;
  a callback that raises fails the run, exactly as any other bug in the call
  path would. There is no "progress must not break analysis" catch that would
  hide a broken reporter.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ProgressEvent"]


@dataclass(frozen=True)
class ProgressEvent:
    """One unit of work an analysis has begun, as a front end can report it.

    Attributes:
        kind: The layer being worked on (``"chords"``, ``"lyrics"``, ...).
        engine: The engine doing it, as provenance records it.
        completed: How many units are finished. A step that reports
            ``total=1`` has *started*, not finished: the service emits the
            completion of a whole-file step as part of the step summary.
        total: How many units the step plans (windows of a chunked run, else
            ``1``).
        detail: A ready-to-print description of the unit, or ``None`` when the
            step has no finer structure than "this layer is running".
    """

    kind: str
    engine: str
    completed: int
    total: int
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.total < 1:
            raise ValueError(f"progress total must be at least 1, got {self.total!r}")
        if not 0 <= self.completed <= self.total:
            raise ValueError(
                f"progress counts must satisfy 0 <= completed <= total, "
                f"got {self.completed!r}/{self.total!r}"
            )

    @property
    def fraction(self) -> float:
        """``completed / total`` in ``[0, 1]``, for a progress bar."""
        return self.completed / self.total
