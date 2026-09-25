# AGENTS.md

Guidance for AI agents (and people) working in this repository.

## What this is

**deskwork** - an agent skill that turns what an agent notices into tracked,
categorised, ordered work on GitHub, and keeps a roadmap in git that says what
comes next and why. It follows the [Agent Skills](https://agentskills.io)
layout (`skills/<name>/SKILL.md`) and ships as a
[Claude Code plugin](https://code.claude.com/docs/en/plugins).

It is the planning half of a pair. [`buildwork`](https://github.com/dbhq-uk/buildwork-skill)
runs the work; deskwork decides what the work is and what order it goes in.

## Layout

```
.claude-plugin/plugin.json          # plugin manifest
skills/deskwork/SKILL.md            # the skill (agent-facing instructions)
skills/deskwork/references/         # issue shapes, Projects v2, config format
skills/deskwork/scripts/            # Python, standard library only
skills/deskwork/tests/              # pytest, no network, no token, no agent
install.sh / install-codex.sh       # local symlink installers
docs/superpowers/specs/             # the dated design record
```

## The constraints that must not be broken

Everything else here is a preference. These are not.

**1. It never closes and never deletes an issue.** No close verb, no delete verb,
no bulk transition. Issues still get closed: `capture` may add `Closes #N` to a
pull request body, and GitHub closes the issue on merge, after a human has
reviewed the work. The skill needs no close verb at all, which is what makes the
constraint hold itself rather than depend on restraint. `gh.py` also refuses,
before `gh` starts, any call that would close, delete or transfer an issue:
`gh issue close|delete|transfer`, a `closeIssue`, `deleteIssue`,
`transferIssue` or `updateIssue` mutation, a write to an issue carrying
`state`, and any `DELETE`.

**2. Agents write only to Triage.** Never assigned, never prioritised, never
`Next` or `In Progress`, and never into the roadmap. Nothing filed unreviewed
may look like committed work. A human moves issues out of Triage after reasoning
has been done.

**3. Destructive Project operations are gated and the gate is re-verified.**
Creating a board, a field or a view is unguarded. Deleting one, or removing an
item, requires: show exactly what goes, re-read it immediately before acting,
and print the IDs so a wrong call is recoverable. A board is worked by several
sessions and moves underneath a listing.

**4. No config file, or no `enabled = true`, means no writes.** Not a warning,
not a prompt. The skill does nothing. `config.load()` returns `None` and the
caller stops at once.

**5. Designs live in git. The issue points at the file.** A design is never
pasted into an issue body. It lives in a file under the `designs:` path from
the config, is versioned and diffable, and the issue links to it from the
Context or Proposal section.

**6. Nothing is inferred into the graph.** An edge exists because it was
proposed and accepted. The reasoning is recorded with it. The `review` mode
gathers the existing graph, the agent proposes edges, and writes happen only
after human approval, one decision per `link`, `unlink`, `reject` or `keep`.
`roadmap` renders the order the agent reasoned, after checking it against the
live graph; it does not compute an order or infer one.

**7. No credential file.** `gh auth` is the credential. There is no
`~/.dbhq/deskwork/`, nothing to leak, and nothing to migrate. Session state is
reconstructed from git and GitHub rather than cached.

**8. Standard library only.** Python standard library plus `gh` 2.94 or later. No PyPI
packages, no venv. This is why the config is TOML - `tomllib` is in the
stdlib and no YAML parser is. Same line `buildwork` holds.

## The identifier hazard

**This is the project's central one.** One GitHub issue carries several identifiers and none is interchangeable:

| Identifier | Looks like | Used by |
|---|---|---|
| Issue number | `144` | humans, URLs, `gh issue` commands |
| Database id | `3527190001` | the REST dependencies API's `issue_id` field |
| GraphQL node id | `"I_kwDOAbc123"` | every Projects v2 mutation |

**The hazard:** Pass an issue number where a database id belongs - `gh api .../issues/144/dependencies/blocked_by` with `issue_id: 144` - and GitHub silently links a different issue in a different repository. The call succeeds. Nothing downstream notices. So deskwork does not use that API at all:

- Edges are written with `gh issue edit N --add-blocked-by M` and `--remove-blocked-by M`. gh takes the number (or, across repositories, the issue URL) and resolves it itself. No database id is ever handled, and no module has a type or a function for one.
- After every edge write the edge list is read back. If it shows anything other than what was asked for, the write is reported as not confirmed, naming the edge that is there and the command that removes it.
- `gh.py` refuses every `DELETE`, so the old REST removal path cannot come back quietly.
- `NodeId` is a distinct Python type, and `require_node_id` refuses a bare string.

Anybody changing code that touches GitHub edges needs this on the page before they start.

## Conventions

- Any path `SKILL.md` names goes through `${CLAUDE_SKILL_DIR}`, which Claude
  Code substitutes for personal, project and plugin installs alike. Always
  with the braces: Claude Code substitutes only that form, and CI fails on
  the unbraced one. **Never
  hardcode `~/.claude/skills/deskwork` or any absolute path** - it is wrong
  under a Codex install and wrong under a plugin install. `install-codex.sh`
  rewrites the variable at install time because Codex does not substitute it.
- `SKILL.md` is the short half on purpose. Workflow and commands live there;
  reasoning and the shape of a good issue live in `references/` and are read on
  demand.
- House style: British English, plain hyphens, **no em dashes** - CI fails on
  them. No trailing full stops on headings.
- Every example is generic: `owner/repo`, `#143`, `PVT_kwDOABCD1234`. CI greps
  for anything resembling a real ticket id, hostname, IP address or
  organisation.

## Where the logic lives

The split is deliberate and worth preserving:

- **Every `gh` call goes through `gh.py`, and every `git` call through
  `git.py`.** Nothing else imports `subprocess`. `repo.py` finds the root with
  `git rev-parse --show-toplevel` and the name from the `origin` remote,
  confirmed by `gh repo view`, so worktrees, subdirectories and forks work.
- **Python does the deterministic half** - config, issue creation, duplicate
  search, graph construction, cycle detection, bottleneck finding, roadmap
  rendering. All of it is tested without a network, a token or an agent.
- **`SKILL.md` does reasoning and approval**, because the agent reasons about
  edges to propose, the human approves, and then the agent tells the script to
  write.

A change that needs human approval knowledge inside a Python module means the
boundary has moved to the wrong place.

## Validating a change

```bash
bash -n install.sh install-codex.sh
jq empty .claude-plugin/plugin.json
python3 -m pytest skills/deskwork/tests -q
grep -rInP '[\x{2014}\x{2013}]' --include='*.md' --include='*.py' --include='*.sh' . && echo "FAIL: dash found" || echo "clean"
grep -rnIF '$CLAUDE_SKILL_DIR' skills/ && echo "FAIL: unbraced" || echo "braced"
grep -rn '/home/\|~/.claude/skills' skills/deskwork/SKILL.md && echo "FAIL: hardcoded path" || echo "no hardcoded paths"
```

All must pass. CI runs those plus the two prose checks.

The tests are worth more than they look. A graph bug does not crash - it returns
a confident wrong order. So the fixtures deliberately include cases that would
produce plausible wrong answers: a cross-repo edge, an issue blocking three
others, an edge whose blocker has closed, a cycle, and the database-ID trap
that `ids.py` exists to prevent.
