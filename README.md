# deskwork

**What an agent notices, filed as tracked work on GitHub - and a roadmap that says what's next**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude_Code-Plugin-blueviolet)](https://code.claude.com/docs/en/plugins)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20WSL-lightgrey)]()

A free, open-source tool by [DBHQ](https://dbhq.uk)

---

An agent skill that turns what an agent notices into tracked, categorised,
ordered work on GitHub, and keeps a roadmap in git that says what comes next
and why.

Three things happen today and none of them survives the session: an agent
finds a side issue while doing something else and mentions it in chat, then it
is gone; an idea gets written into a spec file and nothing tracks whether it
was ever acted on; nobody can say what order the open work should be done in,
because the dependencies are stated in prose rather than declared.

deskwork closes all three. It files the side issue without stopping the task,
links a design file to the issue that tracks it, and reasons about precedence,
writing the conclusion back to GitHub as real dependency links.

## Status

Early scaffold. The skill itself is not yet implemented -
`skills/deskwork/SKILL.md` is a stub.

## Skills

| Skill | What it does |
|---|---|
| [deskwork](skills/deskwork) | File what an agent notices as a tracked GitHub issue, reconcile the dependency graph, and keep a roadmap in git |

## Licence

MIT. See [LICENSE](LICENSE).
