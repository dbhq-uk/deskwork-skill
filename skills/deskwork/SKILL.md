---
name: deskwork
description: File what an agent notices as a tracked GitHub issue, reconcile the dependency graph, and keep a roadmap in git. Trigger on phrases like "deskwork", "file an issue for that", "log that as an issue", "raise a GitHub issue", "track that as an issue", "what's blocking this issue", "reconcile the dependency graph", "refresh the roadmap".
---

# deskwork - turn what an agent notices into tracked work

File side issues without stopping the task, record what blocks what with a reason, and keep a `roadmap.md` in git that says what comes next and why.

## When not to use

- Not for Jira or Confluence. Use `atlassian`.
- Not for Trello. Use `trello`.
- Not in a repository that has not opted in. Say so and stop; offer `init`.
- Not to close, delete, assign or prioritise an issue. deskwork never does any of these.

## Start here

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" doctor
```

| Exit | Means | Do |
|---|---|---|
| 0 | Done, or no drift | Carry on |
| 1 | Refused, or drift found | Read the message; `init` or `intake` fixes most drift |
| 2 | Not opted in | Say so and stop. Offer `init` |
| 3 | The config file is wrong | Show the message |
| 4 | Written, and not as asked | Stop. Do not retry: the message names what exists |
| 10 | `capture` found possible duplicates | Read them, then comment or re-run with `--file` |

Run it from anywhere in the repository, a worktree included. Issues go to the repository the `origin` remote points at.

## capture - file an issue

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" capture --template --type Bug > body.md
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" capture --title "Retry logic drops the last attempt" --type Bug --area infra --body-file body.md
```

1. Read the files, tests and recent commits first, and cite them in the body.
2. Fill every section `--template` printed. A body that still says `_not stated_`, or lacks a section its type needs, is refused.
3. A design goes in a file under the config's `designs` path, linked from Context. Never in the body.
4. `--type` must be a configured type (default `Task`); `--area` a configured area. `--parent 3` makes a sub-issue. Use `--blocked-by 5` only when the body states the dependency as a fact.

It checks for duplicates before filing. Exit 10 means it filed nothing and printed the candidates. If one is this issue, comment on it; if none is, re-run with `--file`. The issue lands in Triage: the Triage label, and Status Triage on the board if there is one. It is read back before `capture` reports success. How to write an issue worth filing: [references/issue-shape.md](references/issue-shape.md).

## review - reconcile the dependency graph

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" review --json
```

Prints every open issue with its blockers and their state, whether it is in Triage, what a human already decided about its edges, the cycles and the bottlenecks. It writes nothing.

You reason about what should block what. The human approves or rejects each proposal. Then record each answer, one edge and one reason at a time:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" link 12 --blocked-by 5 --reason "The migration needs the schema"   # approved addition
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" unlink 12 --blocked-by 5 --reason "No longer needed"               # approved removal
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" reject 12 --blocked-by 5 --reason "Different areas"                # rejected addition
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" keep 12 --blocked-by 5 --reason "Order matters here"               # rejected removal
```

Never propose adding an edge remembered as `rejected` or `unlinked`, or removing one remembered as `deliberate`. Never write an edge with `gh api`. The whole flow: [references/graph-and-roadmap.md](references/graph-and-roadmap.md).

## roadmap - write the order, with reasons

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" roadmap --order order.json
```

`order.json` is your reasoned order, first thing first: `[{"ref": "#7", "reason": "Unblocks the migration"}, ...]`. An entry that is closed, in Triage, blocked, in another repository, repeated or without a reason gets the whole order refused, by name. Otherwise it writes `roadmap.md` with the reason under each item and commits that file alone. `--dry-run` previews, with or without an order. buildwork runs what is under `## Next`.

## init, intake, doctor

- `init` with no config writes `.github/deskwork.toml` switched off, and stops. A human sets `enabled = true` and commits it. Run again, it creates the labels `capture` applies and, with a board, the Triage option on Status. It reports only what it created.
- `intake` puts open issues that are not on the board onto it. Only for a repository with a board.
- `doctor` reports drift in labels, issue types and the board, and exits 1 if there is any.

Every mode that writes takes `--dry-run`.

## The config

`.github/deskwork.toml`, committed. `init` writes the starter, [deskwork.toml.example](deskwork.toml.example), which explains each key. A board is optional: without `project`, the Triage label alone marks what is unreviewed.

## Reference

- [references/issue-shape.md](references/issue-shape.md) - how to write an issue worth filing
- [references/graph-and-roadmap.md](references/graph-and-roadmap.md) - review, the four verbs, memory and the roadmap
- [references/projects-v2.md](references/projects-v2.md) - boards, and the identifiers an issue carries

## Requirements

`git`, `gh` 2.94 or later (authenticated, with the `project` scope for board work), and Python 3.11 or later. No packages.
