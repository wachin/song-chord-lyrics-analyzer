# Troubleshooting

Start with the environment report; it answers most questions immediately:

```bash
songlab doctor
```

## Exit codes

| Code | Meaning | Typical cause |
| --- | --- | --- |
| `0` | success | — |
| `1` | unexpected internal error | a bug; re-run with `--debug` for the traceback |
| `2` | invalid input | wrong path, a directory instead of a file, unknown command, corrupt audio |
| `3` | missing dependency | FFmpeg/ffprobe not found for a non-WAV file |
| `130` | interrupted | `Ctrl+C` |

Run any command with `--debug` to get full logging plus a traceback. Use
`--verbose` for debug logging without tracebacks and `--quiet` for warnings and
errors only.

## "FFprobe was not found" / exit code 3

Only WAV metadata can be read without FFmpeg. To inspect MP3, FLAC, M4A, OGG and
friends, install FFmpeg:

```bash
# Debian / Ubuntu
sudo apt install ffmpeg
# Fedora
sudo dnf install ffmpeg
# Arch
sudo pacman -S ffmpeg
# macOS
brew install ffmpeg
# Windows
winget install --id Gyan.FFmpeg
choco install ffmpeg
scoop install ffmpeg
```

If the binaries are installed somewhere unusual, point the program at them
directly:

```bash
# Linux / macOS
export SONGLAB_FFMPEG=/opt/ffmpeg/bin/ffmpeg
export SONGLAB_FFPROBE=/opt/ffmpeg/bin/ffprobe
```

```powershell
# Windows PowerShell
$env:SONGLAB_FFMPEG = "C:\ffmpeg\bin\ffmpeg.exe"
$env:SONGLAB_FFPROBE = "C:\ffmpeg\bin\ffprobe.exe"
```

## "Unsupported or unreadable audio file"

The container was found but could not be decoded as audio. Common causes:

* the file is a video container without an audio stream;
* the download is truncated (check `songlab info --hash` against the expected
  digest);
* the extension is misleading — probing decides the truth, not the extension.

## "Audio file is empty"

The path exists but the file has zero bytes; re-copy or re-download it.

## Wrong or missing tags

Tags are informational and are deliberately kept separate from technical
metadata. `songlab info` reports codec, sample rate, channels, bit depth,
bitrate, duration and size from the decoder, and shows container tags afterwards
under "Tags (informational, never trusted)". A wrong ID3 title is never used for
analysis.

## Analysis takes too long or runs out of memory

Feature-specific guidance arrives with the engines (phases 3-8). Current
mitigations: use `songlab info` for metadata-only work, and remember that models
are cached under `SONGLAB_CACHE_DIR` (`songlab doctor` prints the path) so a
second run does not re-download anything.

## Where are caches and downloads stored?

```bash
songlab doctor    # prints cache, data, models, exports and temp directories
```

Override them with `SONGLAB_CACHE_DIR`, `SONGLAB_DATA_DIR` and
`SONGLAB_TEMP_DIR`. No path is ever hard-coded per operating system.

## Reporting a problem

Include the output of `songlab doctor`, the exact command, the exit code and the
`--debug` output. Attach audio only if its licence allows redistribution.
