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
  # block 2: instrument recognition — kept after investigation (2026-09-24); the other
  # ten clones of the original block were removed (docs/DEPENDENCY_MATRIX.md §13.8)
  "instrument-prediction|https://github.com/biboamy/instrument-prediction"
  "predominant-instrument-recognition|https://github.com/nii-yamagishilab/predominant-instrument-recognition"
  # block 3 was removed entirely on 2026-09-24 (docs/DEPENDENCY_MATRIX.md §13.9):
  # muscriptor carries CC BY-NC 4.0 weights, presto/shazam-build/audd-go address song
  # identification this project does not need, and Ear is an LLM demo.
  # block 4: cross-cutting libraries
  "libcantus|https://github.com/libraz/libcantus"
  "basic-pitch|https://github.com/spotify/basic-pitch"
  "basic-pitch-ts|https://github.com/spotify/basic-pitch-ts"
)
# https://github.com/yuval-kahan/youchords-local (formerly roadmap section 24.2) no
# longer exists on GitHub (HTTP 404, checked 2026-09-23; dropped from the roadmap on
# 2026-09-24) and is intentionally not registered.
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
