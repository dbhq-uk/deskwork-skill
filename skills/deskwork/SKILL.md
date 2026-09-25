---
name: deskwork
description: File what an agent notices as a tracked GitHub issue, reconcile the dependency graph, and keep a roadmap in git. Trigger on phrases like "file that", "raise an issue", "what's queued", "what should we do next", "refresh the roadmap", "check dependencies", "what's blocking this".
---

# deskwork - turn what an agent notices into tracked work

You file side issues without stopping the task, link design files to the issues that track them, reason about work order, and keep a `roadmap.md` in git saying what comes next and why.

Before anything:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" doctor
```

Exit 2 means this repository has not opted in: no `.github/deskwork.toml`, or no `enabled = true` in it. Say so and stop. Offer `init`, which writes a starter file switched off. Exit 1 from `doctor` means drift, which it names line by line; `init` or `intake` fixes most of it.

## Modes

### capture - file a new issue

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" capture --template --type Bug > body.md
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" capture --title "Retry logic drops the last attempt" --type Bug --area infra --body-file body.md
```

The type is one of the configured `issue_types` and defaults to `Task`. The area is one of the configured areas and is optional. `--parent 3` files it as a sub-issue; `--blocked-by 5,owner/repo#9` declares blockers, but only when the body states the dependency as a fact. Anything that needs judgement goes through `review`.

**Before writing the body:**

1. Read the relevant files, tests and recent commits. An issue written from a hunch is one a later agent has to unpick.
2. Cite what you found in the body: a file path, a test name, a commit.

**The body:** `--template` prints the sections for the type: Context and Acceptance for a Task, plus Expected and Actual for a Bug, plus Proposal and Out of scope for a Feature. Fill every one. A body that still says `_not stated_`, or lacks a section its type needs, is refused before anything is written. Acceptance criteria are checkable statements - true or false once the work is done, not directions to head in.

**Designs go to a file, never into the body.** If the change needs a design - more than a paragraph, a sequence of steps, a diagram - write it to a file under `designs` in the config and link to it from Context.

**Duplicates are checked before filing.** `capture` compares the title with every open issue, and asks GitHub's hybrid search, which also sees issues closed in the last 30 days. If anything looks like the same issue, it files nothing, prints the candidates as JSON, and exits 10. Read them. If one is this issue, comment on it instead. If none is, run the same command again with `--file`.

**What it writes:** the issue, with the `triage` label and the area label, then reads it back and checks the title, body, type, labels, parent and blockers. With a board configured, it also adds the issue to the board and sets Status to Triage, and reads that back. Never assigned, never prioritised, never anything but Triage. If a check fails after the issue exists, `capture` exits 4 and names the issue: do not file it again.

### review - reconcile the dependency graph

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" review --repo . --json
```

Reads every open issue in one query and prints it: each issue's blockers with their state (a closed blocker blocks nothing), its type, parent and labels, whether it is still in Triage, and what a human already decided about its edges. Also the cycles, and the bottlenecks (anything blocking three or more issues). It writes nothing. Without `--json` it prints the same as text.

**The division of labour is strict:**

- **The script** reads and prints. Nothing else.
- **The agent** reasons about what should block what, citing the issues and what you are trying to accomplish.
- **You** approve or reject each proposal. You have the final say on precedence.
- **The script** writes one approved decision at a time, reads it back, and records the reason on the issue.

**The flow:**

1. Run `review --json`.
2. Read every open issue and any design file it links to.
3. Reason about what blocks what. Do not propose adding an edge remembered as `rejected` or `unlinked`, or removing one remembered as `deliberate`.
4. **Show proposed additions and removals, and wait for approval.** The reasoning is how an edge is born.
5. Record each answer with one of the verbs below. Never write an edge with `gh api` directly.

**The verbs, one edge and one reason each:**

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" link 12 --blocked-by 5 --reason "The migration needs the schema"   # approved addition
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" unlink 12 --blocked-by 5 --reason "No longer needed"               # approved removal
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" reject 12 --blocked-by 5 --reason "Different areas"                # rejected addition
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" keep 12 --blocked-by 5 --reason "Order matters here"               # rejected removal
```

`link` and `unlink` write through `gh issue edit`, then read the edge list back. If GitHub shows anything other than what was asked for, the command exits 4 and names the edge that is there, with the command that removes it. `reject` and `keep` change no edge. All four record the decision and the reason in a single `<!-- deskwork -->` comment on the issue, edited in place and read back. The blocker can be in another repository: `--blocked-by owner/repo#9`. `--dry-run` shows what would be written.

### roadmap - write the order, with reasons

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" roadmap --repo . --order order.json
```

The order is yours to reason, not the script's to compute. `order.json` is a list, first thing first:

```json
[{"ref": "#7", "reason": "Unblocks the migration and the reports"},
 {"ref": "#6", "reason": "Free now that its blocker has closed"}]
```

`roadmap` checks every entry against the live graph and refuses the whole order, naming each problem, if an entry is closed, still in Triage, blocked by an open issue, in another repository, repeated, or has no reason. Otherwise it writes `roadmap.md` at the repository root with the reason under each item, and commits that file alone. `--order -` reads the order from stdin. `--dry-run` prints the roadmap instead, and works without an order, to preview.

The sections are `## Next` (your order, and only your order), `## Blocked`, `## Later` (ready but not ordered this time), `## Cycles`, `## Bottlenecks` and `## Triage`. buildwork runs what is under `## Next`, so nothing unreviewed or blocked is ever put there. A Triage issue appears only under `## Triage`, listed and never ordered, until a human moves it out.

### init - opt in and set up

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" init
```

In a repository with no config, `init` writes `.github/deskwork.toml` with `enabled = false` and stops. A human edits it, sets `enabled = true` and commits it. Run `init` again and it creates the labels `capture` applies (the Triage label, and `area:NAME` for each area) and, with a board configured, adds the Triage option to the board's Status field, keeping every existing option. It reports only what it created, so a second run says nothing was created. `--dry-run` shows what it would create.

### intake - put existing issues on the board

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" intake
```

Adds every open issue that is not on the board, then reads the board back. Only for a repository with a board configured and issues from before deskwork. `--dry-run` lists them.

### doctor - report drift

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" doctor
```

Checks labels the config names and the repository lacks, `area:` labels the repository has and the config does not, issue types the config names and the repository has not enabled, and, with a board, the Triage option on Status and open issues missing from the board. Exits 1 on any drift or a missing `project` scope, and 0 when everything matches.

## The config file

`.github/deskwork.toml`, committed to the repository it governs. `init` writes a starter.

```toml
enabled = true                      # required; file presence alone arms nothing
roadmap = "roadmap.md"
designs = "docs/designs/"
issue_types = ["Bug", "Feature", "Task"]   # [] in a personal repository
triage_label = "triage"             # an issue carrying it is unreviewed

[labels]
area = ["infra", "docs"]            # capture --area infra applies area:infra

# Optional: a Projects v2 board, by node id, never by title.
# project = "PVT_kwDOABCD1234"
# triage_status = "Triage"
```

Without `project`, deskwork works from labels alone. An issue is in Triage while it carries the Triage label, or while its Status on the board is Triage. A human takes it out of Triage by removing the label and, with a board, moving its Status.

## Reference

- [references/issue-shape.md](../references/issue-shape.md) - how to write an issue worth filing
- [references/projects-v2.md](../references/projects-v2.md) - the three identifiers and why they matter

## Requirements

`git`, `gh` 2.94 or later (authenticated, with the `project` scope for board work), and Python 3.11 or later for `tomllib`. No packages, no venv. deskwork refuses to run on an older `gh`.

`--repo` takes any path inside the repository: the root, a subdirectory or a worktree all find the same config. Issues are filed in the repository the `origin` remote points at, whatever other remotes the clone has.
