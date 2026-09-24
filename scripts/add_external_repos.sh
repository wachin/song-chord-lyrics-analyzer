#!/usr/bin/env bash
#
# Add the third-party reference repositories listed in ROADMAP.md section 24 as
# git submodules under external/.
#
# These are read-only study references: they are never imported, packaged,
# installed, linted or tested. See external/README.md and AGENTS.md.
#
# Usage:
#   scripts/add_external_repos.sh            # add missing submodules (shallow)
#   scripts/add_external_repos.sh --update   # fetch the pinned commits
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# "path<TAB>url" pairs. Keep in sync with .gitmodules (the authoritative list)
# and external/README.md. Grouped in the same four blocks as external/README.md:
# chords, practice tools and visualization / instrument recognition and detection /
# transcription, audio and other / cross-cutting libraries.
REPOS=(
  # block 1: chords, practice tools and visualization
  # (chord-extractor, Chord-recognition, scales-chords and chordscope were removed on
  # 2026-09-24 after their investigation; verdicts in docs/DEPENDENCY_MATRIX.md §13)
  "Chords.py|https://github.com/yuval-kahan/Chords.py"
  "chordify|https://github.com/1ucas/chordify"
  "MOSS-Music|https://github.com/OpenMOSS/MOSS-Music"
  "orchidas-Chord-Recognition|https://github.com/orchidas/Chord-Recognition"
  "ChordVisualizer|https://github.com/manh9011/ChordVisualizer"
  "musicpractice|https://github.com/atinm/musicpractice"
  "Guitariz|https://github.com/Guitariz/Guitariz"
  "ChordMiniApp|https://github.com/ptnghia-j/ChordMiniApp"
  # block 2: instrument recognition and detection
  "Music-Instrument-Recognition|https://github.com/dhivyasreedhar/Music-Instrument-Recognition"
  "music-instrument-classifier|https://github.com/IvyZX/music-instrument-classifier"
  "Musical-Instrument-Recognition-by-XGBoost|https://github.com/Jay-Codeman/Musical-Instrument-Recognition-by-XGBoost"
  "babaktr-musical-instrument-recognition|https://github.com/babaktr/musical-instrument-recognition"
  "instrument-prediction|https://github.com/biboamy/instrument-prediction"
  "Instrument-Recognition-with-CNNs|https://github.com/bt-s/Instrument-Recognition-with-CNNs"
  "predominant-instrument-recognition|https://github.com/nii-yamagishilab/predominant-instrument-recognition"
  "bronzelion-musical-instrument-recognition|https://github.com/bronzelion/musical-instrument-recognition"
  "instrument-recognition-polyphonic|https://github.com/vskadandale/instrument-recognition-polyphonic"
  "instrument-recogniton|https://github.com/vk-mittal14/instrument-recogniton"
  "instrument-classifier|https://github.com/LMicol/instrument-classifier"
  "Musical-Instrument-Detection|https://github.com/KunalDhawan/Musical-Instrument-Detection"
  # block 3: transcription, audio identification and other
  "muscriptor|https://github.com/muscriptor/muscriptor"
  "presto|https://github.com/skulklabs/presto"
  "shazam-build|https://github.com/Danztee/shazam-build"
  "audd-go|https://github.com/AudDMusic/audd-go"
  "Ear|https://github.com/Kaidorespy/Ear"
  # block 4: cross-cutting libraries
  "libcantus|https://github.com/libraz/libcantus"
  "basic-pitch|https://github.com/spotify/basic-pitch"
  "basic-pitch-ts|https://github.com/spotify/basic-pitch-ts"
)
# Roadmap section 24.2 lists https://github.com/yuval-kahan/youchords-local, which
# returned HTTP 404 on 2026-09-23. It is intentionally not added until the roadmap
# points at the correct repository.
#
# This pool is temporary: after a repository has been investigated and its verdict
# recorded, REMOVE it (git submodule deinit -f external/<name> && git rm -f
# external/<name> && rm -rf .git/modules/external/<name>). See external/README.md.

mode="add"
case "${1:-}" in
  --update) mode="update" ;;
  "" ) ;;
  *) echo "usage: $0 [--update]" >&2; exit 2 ;;
esac

failures=0
for entry in "${REPOS[@]}"; do
  name="${entry%%|*}"
  url="${entry#*|}"
  path="external/${name}"

  if [[ "$mode" == "update" ]]; then
    echo "update ${path}"
    git submodule update --init --depth 1 -- "$path" || failures=$((failures + 1))
    continue
  fi

  if [[ -e "$path" ]]; then
    echo "skip   ${path} (already present)"
    continue
  fi

  echo "add    ${path} <- ${url}"
  if ! git submodule add --depth 1 "$url" "$path"; then
    echo "FAILED ${path} <- ${url}" >&2
    failures=$((failures + 1))
  fi
done

echo
git submodule status --recursive || true

if (( failures > 0 )); then
  echo
  echo "${failures} repository/repositories could not be added. Check the URL and" >&2
  echo "your network access; the rest of the project does not depend on them." >&2
  exit 1
fi

cat <<'EOF'

Reference repositories are read-only material. Do not import, install, package,
lint, test or copy from external/ - see AGENTS.md and external/README.md.
EOF
