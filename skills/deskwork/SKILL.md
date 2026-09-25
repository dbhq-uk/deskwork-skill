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

No `.github/deskwork.toml`, or no `enabled = true` in it, means this repository has not opted in. Say so and stop. Offer `init` if they want one.

## Modes

### capture - file a new issue

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" capture --repo . --title "Title goes here" --type Task --area infra
```

The issue type (`Bug`, `Feature`, `Task`) is optional; it defaults to `Task`. The area is one of your configured area labels; it is optional.

**Before writing the body:**

1. Read the relevant files, tests and recent commits. An issue written from a hunch is one a later agent has to unpick.
2. Search for duplicates - `capture` shows similar open issues and you decide whether to file or comment on an existing one. It never blocks.
3. Cite what you found in the body - a file path, a test name, a commit.

**The body structure:**

`body_for` generates the sections (Context and Acceptance for a Task, additional sections for Bug and Feature). Fill them. The acceptance criteria are checkable statements - something true or false once the work is done, not directions to head in.

**Designs go to a file, never into the body:**

If the change needs a design - more than a paragraph, a sequence of steps, a diagram - write it to a file under `designs:` in your config and link to it from the issue's Context section. A file is versioned and diffable. An issue body is a summary with a pointer in it.

The created issue lands on the board in Triage status. Never assigned. Never prioritised. Never `Next` or `In Progress`.

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

### init - set up labels, fields and board

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" init --repo .
```

Creates the declared labels, fields and statuses on the board. Idempotent - safe to re-run after a config change. This is how a new repository is onboarded in one command.

### intake - add existing issues to the board

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" intake --repo .
```

Bulk-adds existing issues that are not yet on the board. Needed once per repository for repositories with prior history.

### doctor - report board drift

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" doctor --repo .
```

Reports drift: issues missing a required field, issues absent from the board, labels present in the repo but not in the config, and the reverse. Board drift is invisible until somebody looks.

## The config file

`.github/deskwork.toml`, committed to the repository it governs. TOML, not YAML - Python's standard library parses TOML and has never parsed YAML.

```toml
enabled = true                      # required; file presence alone arms nothing
project = "PVT_kwDOABCD1234"        # the Project NODE ID, never its title
designs = "docs/superpowers/specs/"
roadmap = "roadmap.md"
issue_types = ["Bug", "Feature", "Task"]
triage_label = "triage"             # an issue carrying it is unreviewed

[labels]
area = ["website", "brand", "infra", "docs", "client"]

[fields]
Status = "Triage"                   # where every agent-filed item lands
Effort = ["S", "M", "L", "XL"]
Risk = ["low", "medium", "high"]
```

The project is recorded by node ID, not by title. Projects v2 titles need not be unique and a project may not be linked to the repository at all. The ID is unambiguous.

`enabled = true` is required. A half-written or copied-in file must not arm the skill.

## Reference

- [references/issue-shape.md](../references/issue-shape.md) - how to write an issue worth filing
- [references/projects-v2.md](../references/projects-v2.md) - the three identifiers and why they matter

## Requirements

`git`, `gh` 2.94 or later (authenticated, with the `project` scope for board work), and Python 3.11 or later for `tomllib`. No packages, no venv. deskwork refuses to run on an older `gh`.

`--repo` takes any path inside the repository: the root, a subdirectory or a worktree all find the same config. Issues are filed in the repository the `origin` remote points at, whatever other remotes the clone has.
