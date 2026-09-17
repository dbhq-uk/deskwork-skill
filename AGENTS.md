# AGENTS.md

Guidance for AI agents (and people) working in this repository.

## What this is

**deskwork** - an agent skill that turns what an agent notices into tracked,
categorised, ordered work on GitHub, and keeps a roadmap in git that says what
comes next and why. It follows the [Agent Skills](https://agentskills.io)
layout (`skills/<name>/SKILL.md`) and ships as a
[Claude Code plugin](https://code.claude.com/docs/en/plugins).

This repository is at the scaffold stage: `skills/deskwork/SKILL.md` is a stub
and the skill itself is not yet implemented.

## Layout

```
.claude-plugin/plugin.json        # plugin manifest
skills/deskwork/SKILL.md          # the skill (agent-facing instructions) - stub for now
skills/deskwork/tests/            # pytest
.github/workflows/ci.yml          # tests, plus the prose checks
.github/dependabot.yml            # GitHub Actions only, weekly
```

## The constraints that must not be broken

**1. Standard library only.** No PyPI packages, no venv, no `requirements.txt`.
Python 3.11 is the floor.

**2. Shell scripts use `set -e`.** Errors go to stderr, output to stdout.

**3. Every example is generic:** `owner/repo`, `#123`. No real hostname, IP
address or organisation. CI greps for anything that looks like one.

**4. House style: British English, plain hyphens, no em dashes or en dashes**
- CI fails on them. No trailing full stop on a heading, tagline, subtitle or
label.

More constraints will be added here as the skill itself is built.

## Validating a change

```bash
jq empty .claude-plugin/plugin.json
python3 -m pytest skills/deskwork/tests -q
```

CI runs those plus the two prose checks.
