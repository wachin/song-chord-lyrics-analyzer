"""A clock the tests move by hand.

Playback position and lyric/chord synchronization are both functions of time.
Substituting this clock keeps those tests deterministic instead of sleeping and
hoping (roadmap Phase C: "deterministic test of the synchronization logic").
"""

from __future__ import annotations

__all__ = ["FakeClock"]


class FakeClock:
    """A monotonic clock whose value only moves when a test advances it."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = float(start)

    def __call__(self) -> float:
        """Read the current time, so the instance can be used as a ``clock``."""
        return self._now

    @property
    def now(self) -> float:
        """Current instant in seconds."""
        return self._now

    def advance(self, seconds: float) -> float:
        """Move the clock forward and return the new instant."""
        if seconds < 0:
            raise ValueError("a monotonic clock cannot go backwards")
        self._now += float(seconds)
        return self._now
