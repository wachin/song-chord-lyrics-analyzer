"""Playback: the transport, and the player that drives PortAudio (Phase A).

Two layers, tested apart:

* :class:`PlaybackTimeline` is pure Python, so position/state/seek/end are pinned
  with a :class:`FakeClock` - no sleeping, no device, no flakiness.
* :class:`SoundDevicePlayer` is driven against a fake ``sounddevice`` module, so
  block feeding, cursor movement, pause/resume, seek and end-of-stream are all
  verified without an audio device. ``load``, ``seek``, ``position`` and
  ``duration`` work even with no backend at all, and that is tested too.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from fixtures.audio import write_sine_wav
from fixtures.clock import FakeClock
from fixtures.fake_sounddevice import install
from song_chord_lyrics_analyzer.audio.decode import decode_audio
from song_chord_lyrics_analyzer.audio.playback import (
    PlaybackState,
    PlaybackTimeline,
    SoundDevicePlayer,
    create_player,
)
from song_chord_lyrics_analyzer.utils.errors import DependencyError, InputError


def _numpy() -> object | None:
    try:
        return importlib.import_module("numpy")
    except ImportError:
        return None


NUMPY = _numpy()
requires_numpy = pytest.mark.skipif(
    NUMPY is None,
    reason="numpy is required for the stream callback (part of the playback extra)",
)


def _mono_wav(directory: Path, *, seconds: float = 1.0) -> Path:
    return write_sine_wav(directory / "tone.wav", seconds=seconds, channels=1, amplitude=0.2)


class TestPlaybackTimeline:
    def test_a_new_timeline_is_stopped_at_zero(self) -> None:
        timeline = PlaybackTimeline(10.0, clock=FakeClock())
        assert timeline.state is PlaybackState.STOPPED
        assert timeline.position == 0.0
        assert timeline.duration == 10.0
        assert timeline.is_finished is False

    def test_the_position_advances_while_playing(self) -> None:
        clock = FakeClock()
        timeline = PlaybackTimeline(10.0, clock=clock)
        timeline.start()
        clock.advance(0.25)
        assert timeline.position == pytest.approx(0.25)

    def test_pausing_freezes_the_position(self) -> None:
        clock = FakeClock()
        timeline = PlaybackTimeline(10.0, clock=clock)
        timeline.start()
        clock.advance(0.5)
        timeline.pause()
        clock.advance(100.0)
        assert timeline.state is PlaybackState.PAUSED
        assert timeline.position == pytest.approx(0.5)

    def test_resuming_continues_from_the_pause(self) -> None:
        clock = FakeClock()
        timeline = PlaybackTimeline(10.0, clock=clock)
        timeline.start()
        clock.advance(0.5)
        timeline.pause()
        clock.advance(3.0)
        timeline.start()
        clock.advance(0.25)
        assert timeline.position == pytest.approx(0.75)

    def test_the_position_never_passes_the_duration(self) -> None:
        clock = FakeClock()
        timeline = PlaybackTimeline(1.0, clock=clock)
        timeline.start()
        clock.advance(60.0)
        assert timeline.position == 1.0

    def test_start_is_idempotent(self) -> None:
        clock = FakeClock()
        timeline = PlaybackTimeline(10.0, clock=clock)
        timeline.start()
        clock.advance(0.5)
        timeline.start()  # must not re-anchor the clock
        clock.advance(0.5)
        assert timeline.position == pytest.approx(1.0)

    def test_seek_clamps_to_the_track(self) -> None:
        timeline = PlaybackTimeline(4.0, clock=FakeClock())
        timeline.seek(-5.0)
        assert timeline.position == 0.0
        timeline.seek(100.0)
        assert timeline.position == 4.0

    def test_seeking_while_playing_re_anchors_the_clock(self) -> None:
        clock = FakeClock()
        timeline = PlaybackTimeline(10.0, clock=clock)
        timeline.start()
        clock.advance(1.0)
        timeline.seek(2.0)
        clock.advance(0.5)
        assert timeline.position == pytest.approx(2.5)

    def test_stop_returns_to_the_start(self) -> None:
        clock = FakeClock()
        timeline = PlaybackTimeline(10.0, clock=clock)
        timeline.start()
        clock.advance(3.0)
        timeline.stop()
        assert timeline.state is PlaybackState.STOPPED
        assert timeline.position == 0.0

    def test_marking_finished_parks_at_the_end(self) -> None:
        timeline = PlaybackTimeline(2.0, clock=FakeClock())
        timeline.start()
        timeline.mark_finished()
        assert timeline.state is PlaybackState.STOPPED
        assert timeline.position == 2.0
        assert timeline.is_finished is True

    def test_playing_again_after_the_end_restarts_from_zero(self) -> None:
        clock = FakeClock()
        timeline = PlaybackTimeline(2.0, clock=clock)
        timeline.start()
        timeline.mark_finished()
        timeline.start()
        assert timeline.position == 0.0
        clock.advance(0.5)
        assert timeline.position == pytest.approx(0.5)

    def test_pause_and_stop_on_a_stopped_timeline_are_no_ops(self) -> None:
        timeline = PlaybackTimeline(2.0, clock=FakeClock())
        timeline.pause()
        timeline.stop()
        assert timeline.state is PlaybackState.STOPPED
        assert timeline.position == 0.0

    def test_a_non_positive_duration_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="duration"):
            PlaybackTimeline(0.0)


class TestPlayerWithoutABackend:
    """`load`/`seek`/`position` must work headlessly; only `play` needs a device."""

    def test_a_new_player_reports_nothing_loaded(self) -> None:
        player = SoundDevicePlayer()
        assert player.state is PlaybackState.STOPPED
        assert player.position() == 0.0
        assert player.duration() == 0.0

    def test_play_without_load_is_an_input_error(self) -> None:
        with pytest.raises(InputError, match="No audio"):
            SoundDevicePlayer().play()

    def test_seek_without_load_is_an_input_error(self) -> None:
        with pytest.raises(InputError, match="No audio"):
            SoundDevicePlayer().seek(1.0)

    def test_loading_a_wav_reports_its_duration(self, tmp_path: Path) -> None:
        player = SoundDevicePlayer()
        audio = player.load(_mono_wav(tmp_path))

        assert audio.channels == 1
        assert player.duration() == pytest.approx(1.0, abs=1e-3)
        assert player.state is PlaybackState.STOPPED
        assert player.position() == 0.0

    def test_seek_moves_the_position_before_playback(self, tmp_path: Path) -> None:
        player = SoundDevicePlayer()
        player.load(_mono_wav(tmp_path))
        player.seek(0.5)
        assert player.position() == pytest.approx(0.5)
        player.seek(100.0)
        assert player.position() == pytest.approx(player.duration())

    def test_stop_returns_the_position_to_zero(self, tmp_path: Path) -> None:
        player = SoundDevicePlayer()
        player.load(_mono_wav(tmp_path))
        player.seek(0.5)
        player.stop()
        assert player.position() == 0.0
        assert player.state is PlaybackState.STOPPED

    def test_a_missing_backend_is_a_dependency_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from song_chord_lyrics_analyzer.audio import playback

        def _unavailable() -> tuple[object, object]:
            raise DependencyError(
                "playback needs sounddevice", hint="pip install sounddevice numpy"
            )

        monkeypatch.setattr(playback, "_import_backend", _unavailable)
        player = SoundDevicePlayer()
        player.load(_mono_wav(tmp_path))
        with pytest.raises(DependencyError, match="pip install"):
            player.play()

    def test_is_available_reports_a_plain_bool(self) -> None:
        assert isinstance(SoundDevicePlayer.is_available(), bool)

    def test_is_available_is_false_without_the_backend(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from song_chord_lyrics_analyzer.audio import playback

        def _unavailable() -> tuple[object, object]:
            raise DependencyError("no sounddevice")

        monkeypatch.setattr(playback, "_import_backend", _unavailable)
        assert SoundDevicePlayer.is_available() is False

    def test_create_player_returns_the_interface(self) -> None:
        player = create_player()
        assert isinstance(player, SoundDevicePlayer)


@requires_numpy
class TestPlayerStream:
    """The stream contract, checked against a fake PortAudio."""

    def _player(self, monkeypatch: pytest.MonkeyPatch) -> tuple[SoundDevicePlayer, object]:
        fake = install(monkeypatch, NUMPY)
        return SoundDevicePlayer(blocksize=500, clock=FakeClock()), fake

    def test_play_opens_and_starts_the_stream(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        player, fake = self._player(monkeypatch)
        player.load(_mono_wav(tmp_path))
        player.play()

        stream = fake.last_stream
        assert stream.active is True
        assert stream.samplerate == 44100
        assert stream.channels == 1
        assert player.state is PlaybackState.PLAYING

    def test_the_stream_receives_the_samples_in_order(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        player, fake = self._player(monkeypatch)
        wav = _mono_wav(tmp_path)
        expected = decode_audio(wav, mono=False).samples
        player.load(wav)
        player.play()

        block = fake.last_stream.pull(500)
        assert [float(value) for value in block[:, 0]] == pytest.approx(expected[:500], abs=1e-6)

    def test_the_position_follows_the_frames_that_played(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        player, fake = self._player(monkeypatch)
        player.load(_mono_wav(tmp_path))
        player.play()

        fake.last_stream.pull(4410)
        assert player.position() == pytest.approx(0.1, abs=1e-6)

    def test_a_stereo_file_opens_a_stereo_stream(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        player, fake = self._player(monkeypatch)
        player.load(write_sine_wav(tmp_path / "stereo.wav", seconds=0.5, channels=2))
        player.play()
        assert fake.last_stream.channels == 2

    def test_the_end_of_the_stream_stops_the_player(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        player, fake = self._player(monkeypatch)
        player.load(_mono_wav(tmp_path, seconds=0.05))  # 2205 frames
        player.play()

        for _ in range(10):
            fake.last_stream.pull(500)
            if fake.last_stream.finished:
                break

        assert fake.last_stream.finished is True
        assert player.state is PlaybackState.STOPPED
        assert player.position() == pytest.approx(player.duration())
        assert player.position() == pytest.approx(0.05, abs=1e-3)

    def test_playing_again_after_the_end_restarts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        player, fake = self._player(monkeypatch)
        player.load(_mono_wav(tmp_path, seconds=0.05))
        player.play()
        for _ in range(10):
            fake.last_stream.pull(500)
            if fake.last_stream.finished:
                break

        player.play()
        assert player.state is PlaybackState.PLAYING
        assert player.position() == 0.0
        assert fake.last_stream.starts == 2

    def test_pause_stops_the_stream_and_freezes_the_position(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        player, fake = self._player(monkeypatch)
        player.load(_mono_wav(tmp_path))
        player.play()
        fake.last_stream.pull(4410)
        player.pause()

        assert fake.last_stream.active is False
        assert player.state is PlaybackState.PAUSED
        assert player.position() == pytest.approx(0.1, abs=1e-6)

    def test_resume_continues_where_it_paused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        player, fake = self._player(monkeypatch)
        player.load(_mono_wav(tmp_path))
        player.play()
        fake.last_stream.pull(4410)
        player.pause()
        player.play()

        assert fake.last_stream.active is True
        block = fake.last_stream.pull(4410)
        expected = decode_audio(_mono_wav(tmp_path), mono=False).samples
        assert [float(value) for value in block[:, 0]] == pytest.approx(
            expected[4410:8820], abs=1e-6
        )

    def test_seek_during_playback_moves_the_cursor(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        player, fake = self._player(monkeypatch)
        wav = _mono_wav(tmp_path)
        expected = decode_audio(wav, mono=False).samples
        player.load(wav)
        player.play()
        player.seek(0.5)

        block = fake.last_stream.pull(500)
        assert [float(value) for value in block[:, 0]] == pytest.approx(
            expected[22050:22550], abs=1e-6
        )

    def test_the_state_callback_is_notified(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        install(monkeypatch, NUMPY)
        states: list[PlaybackState] = []
        player = SoundDevicePlayer(blocksize=500, on_state_change=states.append)
        player.load(_mono_wav(tmp_path))
        player.play()
        player.pause()
        player.play()
        player.stop()

        assert states == [
            PlaybackState.PLAYING,
            PlaybackState.PAUSED,
            PlaybackState.PLAYING,
            PlaybackState.STOPPED,
        ]

    def test_the_callback_fires_when_the_track_ends(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        install(monkeypatch, NUMPY)
        states: list[PlaybackState] = []
        player = SoundDevicePlayer(blocksize=500, on_state_change=states.append)
        player.load(_mono_wav(tmp_path, seconds=0.05))
        player.play()
        stream = player._stream
        for _ in range(10):
            stream.pull(500)
            if stream.finished:
                break

        assert states == [PlaybackState.PLAYING, PlaybackState.STOPPED]
        assert player.position() == pytest.approx(player.duration())

    def test_set_state_callback_can_be_cleared(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        install(monkeypatch, NUMPY)
        states: list[PlaybackState] = []
        player = SoundDevicePlayer(blocksize=500)
        player.set_state_callback(states.append)
        player.load(_mono_wav(tmp_path))
        player.play()
        player.set_state_callback(None)
        player.stop()

        assert states == [PlaybackState.PLAYING]

    def test_playing_twice_does_not_open_a_second_stream(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        player, fake = self._player(monkeypatch)
        player.load(_mono_wav(tmp_path))
        player.play()
        player.play()

        assert len(fake.streams) == 1
        assert fake.last_stream.starts == 1

    def test_close_releases_the_stream(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        player, fake = self._player(monkeypatch)
        player.load(_mono_wav(tmp_path))
        player.play()
        player.close()

        assert fake.last_stream.closed is True

    def test_a_context_manager_closes_the_stream(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = install(monkeypatch, NUMPY)
        with SoundDevicePlayer(blocksize=500) as player:
            player.load(_mono_wav(tmp_path))
            player.play()
        assert fake.last_stream.closed is True
