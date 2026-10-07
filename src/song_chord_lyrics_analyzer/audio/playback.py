"""Audio playback: turn decoded samples into sound and report the playhead.

Phase A asks for a playback abstraction with ``load``, ``play``, ``pause``,
``seek``, ``position()``, ``duration()`` and state callbacks, and explicitly
wants no Qt types in it: the GUI and the CLI both talk to this interface.

The module is split so the interesting part is testable without any hardware:

* :class:`PlaybackTimeline` is pure Python - a duration, a state and a playhead
  driven by an injectable clock. Pause, resume, seek and end-of-track are
  decided here, deterministically, with a fake clock in the tests.
* :class:`SoundDevicePlayer` is the only backend today: it decodes through
  :func:`~song_chord_lyrics_analyzer.audio.decode.decode_audio` and streams
  blocks to PortAudio with ``sounddevice``. That dependency is optional and
  imported lazily, so ``load``/``seek``/``position`` work headlessly while
  ``play`` reports an honest
  :class:`~song_chord_lyrics_analyzer.utils.errors.DependencyError` when it is
  missing (roadmap Phase A: a player that works only on the developer's machine
  is not complete; a missing device must be reported, not hidden).

``sounddevice`` is MIT-licensed; see ``docs/DEPENDENCY_MATRIX.md``.
"""

from __future__ import annotations

import importlib
import time
from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from song_chord_lyrics_analyzer.audio.decode import DecodedAudio, decode_audio
from song_chord_lyrics_analyzer.utils.errors import DependencyError, InputError
from song_chord_lyrics_analyzer.utils.logging import get_logger

__all__ = [
    "PlaybackState",
    "PlaybackTimeline",
    "Player",
    "SoundDevicePlayer",
    "create_player",
]

_logger = get_logger("audio.playback")

_BACKEND_HINT = (
    "Install the optional playback backend (pip install sounddevice numpy) and "
    "make sure an audio output device is available."
)


class PlaybackState(str, Enum):
    """Where a player is in the track."""

    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"


class PlaybackTimeline:
    """The playhead of one track: position, duration and state.

    Deterministic and dependency-free. While :attr:`state` is ``PLAYING`` the
    position advances with the injected ``clock``; pausing freezes it, seeking
    moves it and ending the track parks it at the duration.
    """

    def __init__(self, duration: float, *, clock: Callable[[], float] | None = None) -> None:
        if duration <= 0:
            raise ValueError(f"duration must be positive, got {duration!r}")
        self._duration = float(duration)
        self._clock = clock if clock is not None else time.monotonic
        self._state = PlaybackState.STOPPED
        self._position = 0.0
        self._anchor: float | None = None

    @property
    def duration(self) -> float:
        """Total length of the track in seconds."""
        return self._duration

    @property
    def state(self) -> PlaybackState:
        """Current playback state."""
        return self._state

    @property
    def position(self) -> float:
        """Current playhead in seconds, interpolated between clock reads."""
        if self._state is PlaybackState.PLAYING and self._anchor is not None:
            elapsed = self._clock() - self._anchor
            return min(self._duration, self._position + max(0.0, elapsed))
        return self._position

    @property
    def is_finished(self) -> bool:
        """Whether the playhead reached the end of the track."""
        return self._state is PlaybackState.STOPPED and self._position >= self._duration

    def start(self) -> None:
        """Begin or resume playback."""
        if self._state is PlaybackState.PLAYING:
            return
        if self._position >= self._duration:
            self._position = 0.0
        self._anchor = self._clock()
        self._state = PlaybackState.PLAYING

    def pause(self) -> None:
        """Freeze the playhead where it is."""
        if self._state is not PlaybackState.PLAYING:
            return
        self._position = self.position
        self._anchor = None
        self._state = PlaybackState.PAUSED

    def stop(self) -> None:
        """Return to the start of the track."""
        self._position = 0.0
        self._anchor = None
        self._state = PlaybackState.STOPPED

    def seek(self, position: float) -> None:
        """Move the playhead to ``position`` seconds, clamped to the track."""
        self._position = min(max(float(position), 0.0), self._duration)
        if self._state is PlaybackState.PLAYING:
            self._anchor = self._clock()

    def mark_finished(self) -> None:
        """Park the playhead at the end after the stream ran out."""
        self._position = self._duration
        self._anchor = None
        self._state = PlaybackState.STOPPED


@runtime_checkable
class Player(Protocol):
    """The playback interface the application layer talks to.

    Deliberately free of GUI types: a future Qt Multimedia backend implements
    this Protocol unchanged (roadmap Phase A/D).
    """

    def load(self, path: str | Path) -> DecodedAudio:
        """Decode ``path`` and make it ready to play."""
        ...

    def play(self) -> None:
        """Start or resume playback."""
        ...

    def pause(self) -> None:
        """Pause playback, keeping the playhead."""
        ...

    def stop(self) -> None:
        """Stop playback and return the playhead to the start."""
        ...

    def seek(self, position: float) -> None:
        """Move the playhead to ``position`` seconds."""
        ...

    def position(self) -> float:
        """Current playhead in seconds."""
        ...

    def duration(self) -> float:
        """Length of the loaded track in seconds."""
        ...

    @property
    def state(self) -> PlaybackState:
        """Current playback state."""
        ...

    def close(self) -> None:
        """Release the audio device."""
        ...


def _import_backend() -> tuple[Any, Any]:
    """Import ``sounddevice`` and numpy, or raise :class:`DependencyError`.

    ``sounddevice`` raises :class:`OSError` when the PortAudio library itself is
    missing, which is a dependency problem, not a crash.
    """
    try:
        sounddevice = importlib.import_module("sounddevice")
        numpy = importlib.import_module("numpy")
    except (ImportError, OSError) as error:
        raise DependencyError(
            "Audio playback needs sounddevice and numpy, which are not available.",
            hint=_BACKEND_HINT,
        ) from error
    return sounddevice, numpy


class SoundDevicePlayer:
    """PortAudio playback backend built on ``sounddevice``.

    Decoding is delegated to the shared decode service; this class only owns the
    stream, the audio cursor and the :class:`PlaybackTimeline`. The stream is
    opened lazily on the first :meth:`play`, so a machine with no output device
    can still load a file, report its duration and seek.
    """

    name = "sounddevice"

    def __init__(
        self,
        *,
        on_state_change: Callable[[PlaybackState], None] | None = None,
        decode: Callable[..., DecodedAudio] = decode_audio,
        clock: Callable[[], float] | None = None,
        blocksize: int = 0,
    ) -> None:
        self._on_state_change = on_state_change
        self._decode = decode
        self._clock = clock
        self._blocksize = blocksize
        self._audio: DecodedAudio | None = None
        self._timeline: PlaybackTimeline | None = None
        self._stream: Any | None = None
        self._sounddevice: Any | None = None
        self._numpy: Any | None = None
        self._cursor = 0
        # Set while the stream is being halted, so the callback neither advances
        # the cursor nor declares the track finished during a pause or a close.
        self._halting = False

    # -- availability ------------------------------------------------------

    @classmethod
    def is_available(cls) -> bool:
        """Whether the backend can import and an output device exists."""
        try:
            sounddevice, _numpy = _import_backend()
        except DependencyError:
            return False
        try:
            sounddevice.query_devices(kind="output")
        except Exception:  # any PortAudio failure means "cannot play here"
            return False
        return True

    # -- interface ---------------------------------------------------------

    def set_state_callback(self, callback: Callable[[PlaybackState], None] | None) -> None:
        """Register (or clear) the callback invoked whenever the state changes."""
        self._on_state_change = callback

    def load(self, path: str | Path, *, mono: bool = False) -> DecodedAudio:
        """Decode ``path`` and prepare it for playback.

        Args:
            path: The audio file to play.
            mono: Downmix to one channel (default keeps the file's channels).

        Raises:
            AudioFileNotFoundError: The path does not exist.
            InputError: The file decodes to no samples.
            UnsupportedAudioError: The file could not be decoded.
            DependencyError: Only the optional DSP stack can decode this file.
        """
        self.close()
        audio = self._decode(path, mono=mono)
        if audio.frame_count == 0:
            raise InputError(
                f"No audio samples could be decoded from {audio.path}.",
                hint="Check that the file is complete and not silent-only in its first window.",
            )
        self._audio = audio
        self._cursor = 0
        self._timeline = PlaybackTimeline(audio.duration, clock=self._clock)
        _logger.debug(
            "loaded %s (%d ch, %d Hz, %.3f s)",
            audio.path,
            audio.channels,
            audio.sample_rate,
            audio.duration,
        )
        return audio

    def play(self) -> None:
        """Start or resume playback, opening the device on first use.

        Raises:
            InputError: No audio has been loaded yet.
            DependencyError: The backend or an output device is unavailable.
        """
        audio = self._require_audio()
        timeline = self._require_timeline()
        if timeline.state is PlaybackState.PLAYING:
            return
        if self._cursor >= audio.frame_count:
            self._cursor = 0
            timeline.seek(0.0)
        stream = self._ensure_stream()
        timeline.start()
        stream.start()
        self._notify()

    def pause(self) -> None:
        """Pause playback, keeping the playhead where it is.

        The playhead is captured *before* the stream is halted and re-applied
        afterwards: stopping a stream makes PortAudio wait for the audio already
        handed to the device, which would otherwise drag the position forward by
        the device buffer (or, with a deep buffer, to the end of the track).
        """
        timeline = self._require_timeline()
        if timeline.state is not PlaybackState.PLAYING:
            return
        playhead = timeline.position
        self._halt()
        self._place_cursor(playhead)
        timeline.pause()
        timeline.seek(playhead)
        self._notify()

    def stop(self) -> None:
        """Stop playback and return the playhead to zero."""
        timeline = self._require_timeline()
        self._halt()
        self._cursor = 0
        timeline.stop()
        self._notify()

    def seek(self, position: float) -> None:
        """Move the playhead to ``position`` seconds."""
        timeline = self._require_timeline()
        target = min(max(float(position), 0.0), timeline.duration)
        self._place_cursor(target)
        timeline.seek(target)

    def position(self) -> float:
        """Current playhead in seconds, or 0.0 when nothing is loaded."""
        return self._timeline.position if self._timeline is not None else 0.0

    def duration(self) -> float:
        """Length of the loaded track in seconds, or 0.0 when nothing is loaded."""
        return self._timeline.duration if self._timeline is not None else 0.0

    @property
    def state(self) -> PlaybackState:
        """Current playback state."""
        return self._timeline.state if self._timeline is not None else PlaybackState.STOPPED

    def close(self) -> None:
        """Close the audio stream, if one is open."""
        stream, self._stream = self._stream, None
        if stream is None:
            return
        self._halting = True
        try:
            stream.close()
        except Exception as error:  # a dying device must not mask the real error
            _logger.debug("closing the playback stream failed: %s", error)
        finally:
            self._halting = False

    def __enter__(self) -> SoundDevicePlayer:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- internals ---------------------------------------------------------

    def _require_audio(self) -> DecodedAudio:
        if self._audio is None:
            raise InputError(
                "No audio is loaded.",
                hint="Call load(path) before using the player.",
            )
        return self._audio

    def _require_timeline(self) -> PlaybackTimeline:
        self._require_audio()
        assert self._timeline is not None  # set together with the audio
        return self._timeline

    def _place_cursor(self, position: float) -> None:
        """Move the sample cursor to ``position`` seconds."""
        audio = self._require_audio()
        self._cursor = min(round(position * audio.sample_rate), audio.frame_count)

    def _halt(self) -> None:
        """Stop pulling audio, discarding what the device has not played yet."""
        stream = self._stream
        if stream is None:
            return
        self._halting = True
        try:
            stream.abort()
        except Exception as error:  # abort is the fast path, stop() the safe one
            _logger.debug("aborting the playback stream failed: %s", error)
            stream.stop()
        finally:
            self._halting = False

    def _ensure_stream(self) -> Any:
        if self._stream is not None:
            return self._stream
        sounddevice, numpy = _import_backend()
        audio = self._require_audio()
        self._sounddevice = sounddevice
        self._numpy = numpy
        try:
            self._stream = sounddevice.OutputStream(
                samplerate=audio.sample_rate,
                channels=audio.channels,
                dtype="float32",
                blocksize=self._blocksize,
                callback=self._callback,
            )
        except Exception as error:
            self._sounddevice = None
            self._numpy = None
            raise DependencyError(
                f"Could not open an audio output stream: {error}",
                hint=_BACKEND_HINT,
            ) from error
        return self._stream

    def _callback(self, outdata: Any, frames: int, time_info: Any, status: Any) -> None:
        """PortAudio asks for the next block; we copy it out of the buffer.

        Runs on PortAudio's callback thread. The end of the track is decided here
        rather than in a ``finished_callback``, so that pausing (which ends with
        the stream finishing) cannot be mistaken for the track ending.
        """
        audio = self._audio
        assert audio is not None
        assert self._sounddevice is not None
        assert self._numpy is not None
        if self._halting:
            outdata.fill(0.0)
            raise self._sounddevice.CallbackStop
        remaining = audio.frame_count - self._cursor
        if remaining <= 0:
            outdata.fill(0.0)
            self._cursor = audio.frame_count
            if self._timeline is not None:
                self._timeline.mark_finished()
            self._notify()
            raise self._sounddevice.CallbackStop
        take = min(frames, remaining)
        first = self._cursor * audio.channels
        block = audio.samples[first : first + take * audio.channels]
        outdata[:take] = self._numpy.asarray(block, dtype="float32").reshape(take, audio.channels)
        if take < frames:
            outdata[take:].fill(0.0)
        self._cursor += take
        # Re-anchor the clock to the frames that actually played, so the reported
        # position stays true instead of drifting with the device buffer.
        if self._timeline is not None:
            self._timeline.seek(self._cursor / audio.sample_rate)

    def _notify(self) -> None:
        if self._on_state_change is not None:
            self._on_state_change(self.state)


def create_player(**kwargs: Any) -> Player:
    """Build the playback backend for this installation.

    ``sounddevice`` is the only backend today; a Qt Multimedia backend for
    Phase D would be selected here. The returned player can always ``load``,
    ``seek`` and report positions - only ``play`` needs a device.
    """
    return SoundDevicePlayer(**kwargs)
