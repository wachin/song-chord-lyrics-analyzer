"""Playback against a real audio device (roadmap Phase A).

The unit tests drive a fake PortAudio; this file proves the same player works
when a device is actually present: it starts a stream, the playhead advances,
pausing freezes it, seeking moves it and the track ends on its own.

CI machines have no audio output, so the module skips unless
``SoundDevicePlayer.is_available()`` is true - the honest version of "works
here", rather than a test that silently does nothing.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import pytest

from fixtures.audio import write_sine_wav
from song_chord_lyrics_analyzer.audio.playback import PlaybackState, SoundDevicePlayer

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(
        not SoundDevicePlayer.is_available(),
        reason="no audio output device (or sounddevice is not installed)",
    ),
]

_TIMEOUT_SECONDS = 5.0


def _wait_for(predicate: Callable[[], bool], *, timeout: float = _TIMEOUT_SECONDS) -> bool:
    """Poll ``predicate`` until it holds or the deadline passes."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def _player(tmp_path: Path, *, seconds: float) -> SoundDevicePlayer:
    player = SoundDevicePlayer(blocksize=1024)
    player.load(write_sine_wav(tmp_path / "tone.wav", seconds=seconds, channels=1, amplitude=0.15))
    return player


def test_the_playhead_advances_while_playing(tmp_path: Path) -> None:
    player = _player(tmp_path, seconds=2.0)
    try:
        player.play()
        assert _wait_for(lambda: player.position() > 0.05), "the playhead never moved"
        assert player.state is PlaybackState.PLAYING
    finally:
        player.close()


def test_pausing_freezes_the_playhead(tmp_path: Path) -> None:
    player = _player(tmp_path, seconds=2.0)
    try:
        player.play()
        assert _wait_for(lambda: player.position() > 0.05), "the playhead never moved"
        player.pause()

        frozen = player.position()
        assert player.state is PlaybackState.PAUSED
        time.sleep(0.15)
        assert player.position() == pytest.approx(frozen, abs=1e-3)
    finally:
        player.close()


def test_resuming_continues_from_the_pause(tmp_path: Path) -> None:
    player = _player(tmp_path, seconds=2.0)
    try:
        player.play()
        assert _wait_for(lambda: player.position() > 0.05), "the playhead never moved"
        player.pause()
        paused = player.position()

        player.play()
        assert _wait_for(lambda: player.position() > paused + 0.02), "resume did not advance"
        assert player.state is PlaybackState.PLAYING
    finally:
        player.close()


def test_seeking_moves_the_playhead(tmp_path: Path) -> None:
    player = _player(tmp_path, seconds=2.0)
    try:
        player.seek(1.0)
        assert player.position() == pytest.approx(1.0, abs=1e-3)

        player.play()
        assert _wait_for(lambda: player.position() > 1.02), (
            "playback did not continue past the seek"
        )

        player.stop()
        assert player.position() == 0.0
        assert player.state is PlaybackState.STOPPED
    finally:
        player.close()


def test_the_track_ends_on_its_own(tmp_path: Path) -> None:
    player = _player(tmp_path, seconds=0.2)
    try:
        player.play()
        assert _wait_for(
            lambda: (
                player.state is PlaybackState.STOPPED and player.position() >= player.duration()
            ),
        ), "the track never reached its end"
        assert player.position() == pytest.approx(0.2, abs=0.02)
    finally:
        player.close()
