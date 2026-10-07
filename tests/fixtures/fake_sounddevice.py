"""A stand-in for the ``sounddevice`` module.

PortAudio cannot be opened on a CI machine, but the player logic still has to be
tested: block counting, cursor movement, end of stream, pause/resume and seek.
This fake exposes the same tiny surface the player uses (``OutputStream`` and
``CallbackStop``) and lets a test "pull" blocks the way PortAudio would.

It needs numpy because the real callback receives a numpy ``outdata`` array.
"""

from __future__ import annotations

from typing import Any

__all__ = ["CallbackStop", "FakeOutputStream", "install"]


class CallbackStop(Exception):
    """Raised by the callback to tell PortAudio the stream is finished."""


class FakeOutputStream:
    """Records the stream lifecycle and replays the callback on demand."""

    def __init__(
        self,
        *,
        samplerate: int,
        channels: int,
        dtype: str,
        blocksize: int,
        callback: Any,
        finished_callback: Any = None,
    ) -> None:
        self.samplerate = samplerate
        self.channels = channels
        self.dtype = dtype
        self.blocksize = blocksize
        self.callback = callback
        self.finished_callback = finished_callback
        self.starts = 0
        self.stops = 0
        self.aborts = 0
        self.closed = False
        self.finished = False
        self.blocks_pulled = 0

    @property
    def active(self) -> bool:
        """Whether the fake stream is running."""
        return self.starts > self.stops + self.aborts

    def start(self) -> None:
        self.starts += 1

    def stop(self) -> None:
        self.stops += 1

    def abort(self) -> None:
        self.aborts += 1

    def close(self) -> None:
        self.closed = True

    def pull(self, frames: int) -> Any:
        """Run one callback pass and return the buffer it filled."""
        import numpy

        outdata = numpy.zeros((frames, self.channels), dtype="float32")
        self.blocks_pulled += 1
        try:
            self.callback(outdata, frames, None, None)
        except CallbackStop:
            self.finished = True
            if self.finished_callback is not None:
                self.finished_callback()
        return outdata


class _FakeModule:
    """The module object handed back where ``sounddevice`` would be imported."""

    CallbackStop = CallbackStop

    def __init__(self) -> None:
        self.streams: list[FakeOutputStream] = []
        self.output_devices = 1

    def OutputStream(self, **kwargs: Any) -> FakeOutputStream:
        """Same shape as ``sounddevice.OutputStream`` (name kept for mocking)."""
        stream = FakeOutputStream(**kwargs)
        self.streams.append(stream)
        return stream

    def query_devices(self, *, kind: str | None = None) -> dict[str, Any]:
        if kind == "output" and self.output_devices <= 0:
            raise ValueError("no output device")
        return {"name": "fake", "index": 0}

    @property
    def last_stream(self) -> FakeOutputStream:
        """The most recently created stream, for assertions."""
        return self.streams[-1]


def install(monkeypatch: Any, module: Any) -> _FakeModule:
    """Patch ``_import_backend`` in the playback module to use the fake.

    Args:
        monkeypatch: The pytest ``monkeypatch`` fixture.
        module: The parsed numpy module to hand back alongside the fake.

    Returns:
        The fake module, so tests can reach its streams.
    """
    from song_chord_lyrics_analyzer.audio import playback

    fake = _FakeModule()
    monkeypatch.setattr(playback, "_import_backend", lambda: (fake, module))
    return fake
