#!/bin/bash
# Install deskwork into ~/.claude/skills/ as a live symlink.
#
# SKILL.md references its scripts via ${CLAUDE_SKILL_DIR}, which Claude Code
# substitutes to the skill's own directory for personal, project and plugin
# installs alike. So this script symlinks the whole skill directory - every
# edit (scripts AND SKILL.md) is immediately live, with no per-file rewrite.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_ROOT="$HOME/.claude/skills"

echo "=== deskwork installer (Claude Code) ==="
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
else
  # tomllib landed in 3.11, and the config is TOML precisely so that no YAML
  # package is needed. An older Python fails at the first config read rather
  # than at install, which is a confusing place to find out.
  if ! python3 -c 'import tomllib' >/dev/null 2>&1; then
    echo "Python $(python3 -V 2>&1 | cut -d' ' -f2) has no tomllib. deskwork needs 3.11 or later."
    echo
  fi
fi

if [ -n "$MISSING" ]; then
  echo "Missing:$MISSING"
  echo "deskwork needs git and an authenticated gh. Install those, then re-run."
  echo
else
  echo "Dependencies OK."
  if ! gh auth status >/dev/null 2>&1; then
    echo "gh is installed but not authenticated. Run: gh auth login"
  fi
fi
echo

# --- Install as a full-directory symlink ---
mkdir -p "$SKILLS_ROOT"
src="$SCRIPT_DIR/skills/deskwork"
target="$SKILLS_ROOT/deskwork"

echo "Installing 'deskwork' -> $target"
rm -rf "$target"            # replace any prior copy or partial-symlink install
ln -sfn "$src" "$target"    # whole-directory symlink; ${CLAUDE_SKILL_DIR} resolves it

echo
echo "Installed as a directory symlink - all edits are live."
echo
echo "deskwork does nothing until a repository opts in. In a repo you want it on:"
echo "  python3 $target/scripts/deskwork.py init"
echo "then set enabled = true in .github/deskwork.toml."
echo
echo "Then try: 'file an issue for that', 'reconcile the dependency graph', or 'refresh the roadmap'"
