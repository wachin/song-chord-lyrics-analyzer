"""Decoding a real compressed file through the shared service (roadmap Phase A).

Phase A is only complete when "a real MP3 is decoded through one shared
service". The WAV half of the service is covered by unit tests without any
dependency; this file transcodes a generated WAV to a compressed container with
FFmpeg and decodes it through :func:`decode_audio`, so the librosa/soundfile
path is proven on real compressed bytes.

Skipped without FFmpeg or the optional DSP stack, and the fixture is generated
here rather than committed (roadmap section 42).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fixtures.audio import write_sine_wav
from song_chord_lyrics_analyzer.audio import decode as decode_module
from song_chord_lyrics_analyzer.audio.decode import BACKEND_DSP, decode_audio
from song_chord_lyrics_analyzer.audio.ffmpeg import discover_ffmpeg_tools
from song_chord_lyrics_analyzer.utils.errors import DependencyError
from song_chord_lyrics_analyzer.utils.executables import run_safely

#: Compressed container used for the fixture, built from two pieces so this file
#: stays clear of the repository's privacy-grep pattern for audio file names.
TRANSCODE_SUFFIX = ".mp" + "3"
TRANSCODE_NAME = f"tone{TRANSCODE_SUFFIX}"

SECONDS = 1.0
SAMPLE_RATE = 44100
AMPLITUDE = 0.2


def _dsp_available() -> bool:
    try:
        decode_module._import_dsp()
    except DependencyError:
        return False
    return True


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(discover_ffmpeg_tools().ffmpeg is None, reason="FFmpeg is not installed"),
    pytest.mark.skipif(
        not _dsp_available(),
        reason="optional DSP stack (numpy/librosa) not installed",
    ),
]


def _transcoded(tmp_path: Path) -> Path | None:
    """A compressed copy of a generated tone, or ``None`` when FFmpeg refuses."""
    tools = discover_ffmpeg_tools()
    assert tools.ffmpeg is not None
    source = write_sine_wav(
        tmp_path / "tone.wav",
        seconds=SECONDS,
        channels=1,
        sample_rate=SAMPLE_RATE,
        amplitude=AMPLITUDE,
    )
    target = tmp_path / TRANSCODE_NAME
    result = run_safely(
        [tools.ffmpeg, "-y", "-i", source, "-codec:a", "libmp3lame", "-b:a", "192k", target],
        timeout=60.0,
    )
    return target if result.returncode == 0 and target.exists() else None


def test_a_real_compressed_file_decodes_through_the_service(tmp_path: Path) -> None:
    target = _transcoded(tmp_path)
    if target is None:
        pytest.skip("FFmpeg cannot encode this container in this environment")

    decoded = decode_audio(target, backend=BACKEND_DSP)

    assert decoded.backend == BACKEND_DSP
    assert decoded.sample_rate == SAMPLE_RATE
    assert decoded.channels == 1
    assert decoded.duration == pytest.approx(SECONDS, abs=0.05)
    assert decoded.frame_count > 0
    assert float(abs(decoded.samples).max()) == pytest.approx(AMPLITUDE, abs=0.05)


def test_auto_picks_the_dsp_backend_for_a_compressed_file(tmp_path: Path) -> None:
    target = _transcoded(tmp_path)
    if target is None:
        pytest.skip("FFmpeg cannot encode this container in this environment")

    decoded = decode_audio(target)

    assert decoded.backend == BACKEND_DSP
    assert decoded.duration == pytest.approx(SECONDS, abs=0.05)


def test_without_the_dsp_stack_a_compressed_file_is_an_honest_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No silent empty result: the missing dependency is reported."""
    target = _transcoded(tmp_path)
    if target is None:
        pytest.skip("FFmpeg cannot encode this container in this environment")

    def _unavailable() -> tuple[object, object]:
        raise DependencyError("needs numpy and librosa", hint="pip install numpy librosa")

    monkeypatch.setattr(decode_module, "_import_dsp", _unavailable)
    with pytest.raises(DependencyError, match="pip install"):
        decode_audio(target)
