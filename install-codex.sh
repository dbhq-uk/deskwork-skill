#!/bin/bash
# Install deskwork into ~/.codex/skills/ for Codex.
#
# Codex does not substitute ${CLAUDE_SKILL_DIR}, so this script rewrites that
# variable to the installed Codex path and symlinks the supporting directories
# (edits to those stay live). Re-run after editing SKILL.md.
#
# There is no build step: deskwork is Python standard library and shells out
# to git and gh.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_ROOT="$HOME/.codex/skills"

echo "=== deskwork installer (Codex) ==="
echo

# --- Dependencies ---
MISSING=""
command -v git >/dev/null 2>&1 || MISSING="$MISSING git"
command -v gh >/dev/null 2>&1  || MISSING="$MISSING gh"

# gh 2.94 added the flags deskwork is built on: --type, --parent and
# --blocked-by on issue create, and --add-blocked-by on issue edit. An older
# gh fails on the first command that uses one, so refuse it here instead.
GH_MIN_MAJOR=2
GH_MIN_MINOR=94
if command -v gh >/dev/null 2>&1; then
  gh_version=$(gh --version 2>/dev/null | sed -n 's/^gh version \([0-9][0-9]*\.[0-9][0-9]*\)\..*/\1/p' | head -n 1)
  gh_major=${gh_version%%.*}
  gh_minor=${gh_version#*.}
  if [ -z "$gh_version" ] || [ "$gh_major" -lt "$GH_MIN_MAJOR" ] || \
     { [ "$gh_major" -eq "$GH_MIN_MAJOR" ] && [ "$gh_minor" -lt "$GH_MIN_MINOR" ]; }; then
    echo "gh ${gh_version:-of unknown version} is too old. deskwork needs gh $GH_MIN_MAJOR.$GH_MIN_MINOR or later."
    echo "Upgrade gh (https://github.com/cli/cli#installation), then re-run. Nothing was installed."
    exit 1
  fi
fi

if ! command -v python3 >/dev/null 2>&1; then
  MISSING="$MISSING python3"
elif ! python3 -c 'import tomllib' >/dev/null 2>&1; then
  echo "Python $(python3 -V 2>&1 | cut -d' ' -f2) has no tomllib. deskwork needs 3.11 or later."
  echo
fi

if [ -n "$MISSING" ]; then
  echo "Missing:$MISSING"
  echo "deskwork needs git and an authenticated gh. Install those, then re-run."
  echo
else
  echo "Dependencies OK."
fi
echo

src="$SCRIPT_DIR/skills/deskwork"
target="$SKILLS_ROOT/deskwork"

mkdir -p "$target"
echo "Installing 'deskwork' -> $target"

# Clear what a previous install left before linking what this one needs.
# Without this, an entry since renamed or deleted upstream survives as a
# symlink to a path that no longer exists - and a dangling link fails more
# confusingly than a missing file, because it looks installed. Only symlinks
# are removed, so a real SKILL.md is never at risk.
find "$target" -mindepth 1 -maxdepth 1 -type l -exec rm -f {} +

for sub in references scripts; do
  [ -d "$src/$sub" ] && ln -sfn "$src/$sub" "$target/$sub"
done

sed "s#\${CLAUDE_SKILL_DIR}#$target#g; s#\$CLAUDE_SKILL_DIR#$target#g" "$src/SKILL.md" > "$target/SKILL.md"

echo
echo "Installed for Codex. Re-run after editing SKILL.md - that file is rewritten"
echo "at install time rather than symlinked, so its edits are not live."
echo
echo "deskwork does nothing until a repository opts in:"
echo "  python3 $target/scripts/deskwork.py init"
echo "then set enabled = true in .github/deskwork.toml."
