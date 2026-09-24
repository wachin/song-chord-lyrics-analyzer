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

# "path<TAB>url" pairs. Keep in sync with ROADMAP.md section 24 and
# external/README.md.
REPOS=(
  "chordify|https://github.com/1ucas/chordify"
  "magic-chords-project|https://github.com/Esysc/magic-chords-project"
  "chordscope|https://github.com/okamyuji/chordscope"
  "Chord-Recognition|https://github.com/orchidas/Chord-Recognition"
  "MOSS-Music|https://github.com/OpenMOSS/MOSS-Music"
)
# Roadmap section 24.2 lists https://github.com/yuval-kahan/youchords-local, which
# returned HTTP 404 on 2026-09-23. It is intentionally not added until the roadmap
# points at the correct repository.

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
