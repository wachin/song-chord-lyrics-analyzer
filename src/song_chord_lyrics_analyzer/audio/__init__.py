"""Audio foundation: validation, probing, decoding and preprocessing.

FFmpeg is the primary compatibility layer, but it is optional: WAV metadata is
readable with the standard library so the CLI works out of the box.
"""

from __future__ import annotations

from song_chord_lyrics_analyzer.audio.ffmpeg import (
    FFMPEG_ENV_VAR,
    FFPROBE_ENV_VAR,
    FfmpegTools,
    discover_ffmpeg_tools,
    ffmpeg_install_hint,
    find_ffmpeg,
    find_ffprobe,
    require_ffprobe,
)
from song_chord_lyrics_analyzer.audio.probe import (
    compute_file_hash,
    probe_audio,
    probe_audio_with_ffprobe,
    probe_audio_with_wave,
)
from song_chord_lyrics_analyzer.audio.validation import (
    SUPPORTED_AUDIO_EXTENSIONS,
    is_probably_audio,
    validate_audio_file,
)

__all__ = [
    "FFMPEG_ENV_VAR",
    "FFPROBE_ENV_VAR",
    "SUPPORTED_AUDIO_EXTENSIONS",
    "FfmpegTools",
    "compute_file_hash",
    "discover_ffmpeg_tools",
    "ffmpeg_install_hint",
    "find_ffmpeg",
    "find_ffprobe",
    "is_probably_audio",
    "probe_audio",
    "probe_audio_with_ffprobe",
    "probe_audio_with_wave",
    "require_ffprobe",
    "validate_audio_file",
]
