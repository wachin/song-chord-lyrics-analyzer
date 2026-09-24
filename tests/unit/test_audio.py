"""Unit tests for the audio foundation (roadmap phases 0 and 2)."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from song_chord_lyrics_analyzer.audio import probe as probe_module
from song_chord_lyrics_analyzer.audio.probe import (
    compute_file_hash,
    probe_audio,
    probe_audio_with_ffprobe,
    probe_audio_with_wave,
)
from song_chord_lyrics_analyzer.audio.validation import is_probably_audio, validate_audio_file
from song_chord_lyrics_analyzer.utils.errors import (
    AudioFileNotFoundError,
    DependencyError,
    InputError,
    UnsupportedAudioError,
)

FFPROBE_PAYLOAD = {
    "streams": [
        {
            "codec_type": "audio",
            "codec_name": "mp3",
            "sample_rate": "44100",
            "channels": 2,
            "bits_per_raw_sample": "16",
            "duration": "225.32",
        }
    ],
    "format": {
        "duration": "225.32",
        "format_name": "mp3",
        "bit_rate": "320000",
        "size": "9000000",
        "tags": {
            "title": "A Song",
            "artist": "An Artist",
            "album": "An Album",
            "genre": "Rock",
            "date": "2020",
            "comment": "kept verbatim",
        },
    },
}


def _fake_ffprobe(stdout: str, returncode: int = 0, stderr: str = ""):
    def _run(args, *, timeout: float = 30.0):  # signature parity with run_ffprobe
        del timeout
        return subprocess.CompletedProcess(
            args=list(args), returncode=returncode, stdout=stdout, stderr=stderr
        )

    return _run


class TestValidation:
    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(AudioFileNotFoundError) as excinfo:
            validate_audio_file(tmp_path / "nope.mp3")
        assert excinfo.value.exit_code == 2

    def test_directory_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(InputError):
            validate_audio_file(tmp_path)

    def test_empty_file_is_rejected(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.wav"
        empty.write_bytes(b"")
        with pytest.raises(InputError):
            validate_audio_file(empty)

    def test_valid_file_is_resolved(self, tone_wav: Path) -> None:
        assert validate_audio_file(tone_wav) == tone_wav.resolve()

    def test_extension_heuristic(self) -> None:
        assert is_probably_audio(Path("song.mp3")) is True
        assert is_probably_audio(Path("SONG.WAV")) is True
        assert is_probably_audio(Path("notes.txt")) is False

    def test_unknown_extension_is_only_warned_about(self, tmp_path: Path) -> None:
        weird = tmp_path / "song.xyz"
        weird.write_bytes(b"data")
        assert validate_audio_file(weird) == weird.resolve()


class TestWaveProbe:
    def test_metadata_from_stdlib(self, tone_wav: Path) -> None:
        document = probe_audio_with_wave(tone_wav)
        assert document.probe_backend == "wave"
        assert document.sample_rate == 44100
        assert document.channels == 2
        assert document.bit_depth == 16
        assert document.format == "wav"
        assert document.codec == "pcm"
        assert document.duration == pytest.approx(1.0, abs=0.01)
        assert document.bitrate == 44100 * 2 * 2 * 8

    def test_corrupt_wav_is_rejected(self, corrupt_wav: Path) -> None:
        with pytest.raises(UnsupportedAudioError):
            probe_audio_with_wave(corrupt_wav)

    def test_mono_metadata(self, tmp_path: Path, make_wav) -> None:
        path = make_wav(tmp_path / "mono.wav", channels=1, seconds=0.5)
        document = probe_audio_with_wave(path)
        assert document.channels == 1
        assert document.channels_label == "mono"


class TestFfprobeProbe:
    def test_payload_is_parsed(self, tmp_path: Path, monkeypatch) -> None:
        audio = tmp_path / "song.mp3"
        audio.write_bytes(b"fake mp3 payload")
        monkeypatch.setattr(probe_module, "run_ffprobe", _fake_ffprobe(json.dumps(FFPROBE_PAYLOAD)))
        document = probe_audio_with_ffprobe(audio)

        assert document.probe_backend == "ffprobe"
        assert document.sample_rate == 44100
        assert document.channels == 2
        assert document.bit_depth == 16
        assert document.format == "mp3"
        assert document.codec == "mp3"
        assert document.bitrate == 320_000
        assert document.file_size == 9_000_000
        assert document.duration == pytest.approx(225.32)
        assert document.title == "A Song"
        assert document.artist == "An Artist"
        assert document.album == "An Album"
        assert document.genre == "Rock"
        assert document.year == "2020"
        assert document.extra_tags == {"comment": "kept verbatim"}

    def test_multi_component_format_name_uses_first_component(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        audio = tmp_path / "song.m4a"
        audio.write_bytes(b"fake payload")
        payload = {
            "streams": [{"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000"}],
            "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "10.0"},
        }
        monkeypatch.setattr(probe_module, "run_ffprobe", _fake_ffprobe(json.dumps(payload)))
        assert probe_audio_with_ffprobe(audio).format == "mov"

    def test_nonzero_exit_is_reported(self, tmp_path: Path, monkeypatch) -> None:
        audio = tmp_path / "song.mp3"
        audio.write_bytes(b"not audio")
        monkeypatch.setattr(
            probe_module,
            "run_ffprobe",
            _fake_ffprobe("", returncode=1, stderr="Invalid data found when processing input"),
        )
        with pytest.raises(UnsupportedAudioError, match="Invalid data"):
            probe_audio_with_ffprobe(audio)

    def test_file_without_audio_stream_is_rejected(self, tmp_path: Path, monkeypatch) -> None:
        audio = tmp_path / "song.mp3"
        audio.write_bytes(b"video only")
        payload = {"streams": [{"codec_type": "video"}], "format": {}}
        monkeypatch.setattr(probe_module, "run_ffprobe", _fake_ffprobe(json.dumps(payload)))
        with pytest.raises(UnsupportedAudioError, match="no audio stream"):
            probe_audio_with_ffprobe(audio)

    def test_invalid_json_is_rejected(self, tmp_path: Path, monkeypatch) -> None:
        audio = tmp_path / "song.mp3"
        audio.write_bytes(b"payload")
        monkeypatch.setattr(probe_module, "run_ffprobe", _fake_ffprobe("<not json>"))
        with pytest.raises(UnsupportedAudioError, match="not JSON"):
            probe_audio_with_ffprobe(audio)


class TestProbeAudioDispatch:
    def test_wav_works_without_ffprobe(self, tone_wav: Path, monkeypatch) -> None:
        monkeypatch.setattr(probe_module, "find_ffprobe", lambda: None)
        document = probe_audio(tone_wav)
        assert document.probe_backend == "wave"

    def test_non_wav_requires_ffprobe(self, tmp_path: Path, monkeypatch) -> None:
        audio = tmp_path / "song.mp3"
        audio.write_bytes(b"payload")
        monkeypatch.setattr(probe_module, "find_ffprobe", lambda: None)
        with pytest.raises(DependencyError) as excinfo:
            probe_audio(audio)
        assert excinfo.value.exit_code == 3
        assert "FFmpeg" in str(excinfo.value)

    def test_ffprobe_is_preferred_when_present(self, tmp_path: Path, monkeypatch) -> None:
        audio = tmp_path / "song.mp3"
        audio.write_bytes(b"payload")
        monkeypatch.setattr(probe_module, "find_ffprobe", lambda: Path("/usr/bin/ffprobe"))
        monkeypatch.setattr(probe_module, "run_ffprobe", _fake_ffprobe(json.dumps(FFPROBE_PAYLOAD)))
        assert probe_audio(audio).probe_backend == "ffprobe"

    def test_wav_falls_back_to_stdlib_when_ffprobe_fails(self, tone_wav: Path, monkeypatch) -> None:
        monkeypatch.setattr(probe_module, "find_ffprobe", lambda: Path("/usr/bin/ffprobe"))
        monkeypatch.setattr(
            probe_module, "run_ffprobe", _fake_ffprobe("", returncode=1, stderr="boom")
        )
        assert probe_audio(tone_wav).probe_backend == "wave"


class TestFileHash:
    def test_hash_matches_hashlib(self, tone_wav: Path) -> None:
        expected = hashlib.sha256(tone_wav.read_bytes()).hexdigest()
        assert compute_file_hash(tone_wav) == expected

    def test_same_content_same_hash(self, tmp_path: Path, make_wav) -> None:
        first = make_wav(tmp_path / "a.wav", seconds=0.2)
        second = make_wav(tmp_path / "b.wav", seconds=0.2)
        assert compute_file_hash(first) == compute_file_hash(second)
