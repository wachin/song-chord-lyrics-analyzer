"""Integration tests for the FFmpeg toolchain (roadmap section 65).

These tests are skipped when FFmpeg is not installed: optional tools must never
make the suite fail on a clean machine (roadmap section 16).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fixtures.audio import write_sine_wav
from song_chord_lyrics_analyzer.audio.ffmpeg import (
    discover_ffmpeg_tools,
    tool_version,
)
from song_chord_lyrics_analyzer.audio.probe import probe_audio, probe_audio_with_ffprobe

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(discover_ffmpeg_tools().ffprobe is None, reason="FFprobe is not installed"),
]


def test_ffprobe_reports_its_version() -> None:
    tools = discover_ffmpeg_tools()
    assert tools.ffprobe is not None
    version = tool_version(tools.ffprobe)
    assert version is not None
    assert "version" in version.lower()


def test_real_ffprobe_probe(tone_wav: Path) -> None:
    document = probe_audio_with_ffprobe(tone_wav)
    assert document.probe_backend == "ffprobe"
    assert document.sample_rate == 44100
    assert document.channels == 2
    assert document.duration == pytest.approx(1.0, abs=0.05)


def test_real_ffprobe_is_used_by_default(tone_wav: Path) -> None:
    assert probe_audio(tone_wav).probe_backend == "ffprobe"


def test_ffprobe_rejects_a_non_audio_file(tmp_path: Path) -> None:
    from song_chord_lyrics_analyzer.utils.errors import UnsupportedAudioError

    junk = tmp_path / "song.mp3"
    junk.write_bytes(b"this is not audio at all" * 10)
    with pytest.raises(UnsupportedAudioError):
        probe_audio_with_ffprobe(junk)


def test_ffprobe_reads_flac_and_mp3_round_trip(tmp_path: Path) -> None:
    """Decode a generated WAV into MP3/FLAC with FFmpeg, then probe the result."""
    tools = discover_ffmpeg_tools()
    if tools.ffmpeg is None:
        pytest.skip("FFmpeg is not installed")

    from song_chord_lyrics_analyzer.utils.executables import run_safely

    source = write_sine_wav(tmp_path / "source.wav", seconds=0.5)

    for suffix, codec_args in (("mp3", ["-codec:a", "libmp3lame"]), ("flac", ["-codec:a", "flac"])):
        target = tmp_path / f"converted.{suffix}"
        result = run_safely([tools.ffmpeg, "-y", "-i", source, *codec_args, target], timeout=60.0)
        if result.returncode != 0:
            pytest.skip(f"FFmpeg cannot encode {suffix} in this environment")

        document = probe_audio(target)
        assert document.format in {suffix, "flac", "mp3"}
        assert document.duration == pytest.approx(0.5, abs=0.1)
        assert document.sample_rate == 44100
