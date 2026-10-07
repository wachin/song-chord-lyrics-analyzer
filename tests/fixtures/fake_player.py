"""A ``Player`` with no audio hardware, driven by a :class:`FakeClock`.

The session's synchronization logic is a function of the playhead, so testing it
must not depend on how fast a device drains its buffer. The fake player wraps
the real :class:`PlaybackTimeline` on a fake clock: the position stays put until
the test calls :meth:`FakePlayer.advance`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fixtures.clock import FakeClock
from song_chord_lyrics_analyzer.audio.decode import DecodedAudio, decode_audio
from song_chord_lyrics_analyzer.audio.playback import PlaybackState, PlaybackTimeline

__all__ = ["FakePlayer"]


class FakePlayer:
    """The playback interface, minus the device."""

    name = "fake"

    def __init__(
        self,
        *,
        clock: FakeClock | None = None,
        decode: Callable[..., DecodedAudio] = decode_audio,
    ) -> None:
        self.clock = clock if clock is not None else FakeClock()
        self._decode = decode
        self.loaded: list[Path] = []
        self.calls: list[str] = []
        self.closed = False
        self.audio: DecodedAudio | None = None
        self.timeline: PlaybackTimeline | None = None

    def advance(self, seconds: float) -> None:
        """Move the clock forward, advancing the playhead while playing."""
        self.clock.advance(seconds)

    def load(self, path: str | Path, *, mono: bool = False) -> DecodedAudio:
        self.calls.append("load")
        self.loaded.append(Path(path))
        audio = self._decode(path, mono=mono)
        self.audio = audio
        self.timeline = PlaybackTimeline(audio.duration, clock=self.clock)
        return audio

    def play(self) -> None:
        self.calls.append("play")
        self._require_timeline().start()

    def pause(self) -> None:
        self.calls.append("pause")
        self._require_timeline().pause()

    def stop(self) -> None:
        self.calls.append("stop")
        self._require_timeline().stop()

    def seek(self, position: float) -> None:
        self.calls.append("seek")
        self._require_timeline().seek(position)

    def position(self) -> float:
        return self.timeline.position if self.timeline is not None else 0.0

    def duration(self) -> float:
        return self.timeline.duration if self.timeline is not None else 0.0

    @property
    def state(self) -> PlaybackState:
        return self.timeline.state if self.timeline is not None else PlaybackState.STOPPED

    def close(self) -> None:
        self.calls.append("close")
        self.closed = True

    def _require_timeline(self) -> PlaybackTimeline:
        if self.timeline is None:
            raise AssertionError("load() must be called before playback")
        return self.timeline
