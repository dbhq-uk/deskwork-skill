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
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" review --repo .
```

This reads every open issue and its links and reports the graph. The script gathers and presents; the agent reasons about what should block what; you (the human) approve or reject; the script writes only after approval.

**The division of labour is strict:**

- **The script** - `review` - reads the board and prints it. Nothing else.
- **The agent** - reasons about what should block what, citing the issues and what you are trying to accomplish.
- **You** - approve proposed edges or reject them. You have the final say on precedence.
- **The script** - writes the approved edges only. Each written edge records its reason in a comment.

The order in the roadmap is reasoned, which is exactly why `roadmap.md` records the date, the issue count, and one line of reasoning per item. If you later disagree with that reasoning, you edit the edges (not the roadmap), and the next render reflects your change.

**The flow:**

1. Run `review` to read the existing graph - every native `blocked-by` and `blocking` link on open issues.
2. Read every open issue and any design file it links to.
3. Reason about what blocks what.
4. **Show proposed additions and wait for approval.** The reasoning is how an edge is born.
5. Show proposed removals and wait for approval.
6. On approval, write the edges. If rejected, note it and do not re-propose the same edge.

**Memory:**

Reject a proposed edge and it is not proposed again. Reject a removal and the edge is marked deliberate. Both are recorded in a single `<!-- deskwork -->` comment on the issue, maintained in place.

**Also reports:**

- Bottlenecks - any issue blocking three or more others
- Cycles - reported as cycles, never hidden
- Decomposition candidates - issues at Effort L or XL with proposed sub-issues

### roadmap - render the roadmap

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" roadmap --repo .
```

Builds the dependency graph and renders `roadmap.md` in the repository root, then commits it. The roadmap shows what is ready to start, what is blocked, and what is still in Triage (not yet reasoned). Order is reasoned, not computed. Every dependency shown is a declared GitHub link.

Items in Triage are listed but never ordered. Nothing filed unreviewed enters the roadmap until a human moves it out.

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

`git`, `gh` (authenticated, with the `project` scope for board work), and Python 3.11 or later for `tomllib`. No packages, no venv.
