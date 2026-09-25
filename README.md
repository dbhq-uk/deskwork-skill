<div align="center">

<img src="assets/logo.svg" alt="deskwork - what an agent noticed, tracked as real work, by DBHQ" width="560">

# deskwork

**What an agent noticed, tracked as real work**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude_Code-Plugin-blueviolet)](https://code.claude.com/docs/en/plugins)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20WSL-lightgrey)]()

A free, open-source tool by [DBHQ](https://dbhq.uk) - documented at [skills.dbhq.uk](https://skills.dbhq.uk/deskwork/)

</div>

---

File what an agent notices as tracked work on GitHub - and keep a roadmap in git that says what comes next and why.

An agent skill for [Claude Code](https://code.claude.com) and [Codex](https://developers.openai.com/codex/cli). File a side issue mid-task without stopping, link designs to the issues that track them, reason about work order, and render a roadmap from the dependency graph.

## What makes it different

Three things happen in most agent workflows and none of them survives the session:

1. An agent finds a side issue while doing something else, mentions it, and it is gone.
2. An idea or a design gets written into a spec file and nothing tracks whether it was acted on.
3. Nobody can say what order open work should be done in because dependencies are stated in prose, not declared.

deskwork closes all three. It files the side issue, links the design file to an issue that tracks it, and reasons about precedence, writing the conclusion back to GitHub as real dependency links.

## Install

### As a Claude Code plugin (recommended)

```
/plugin marketplace add dbhq-uk/marketplace
/plugin install deskwork@dbhq
```

### Any agent (Cursor, Copilot, Windsurf, Gemini, Cline and more)

```bash
npx skills add dbhq-uk/deskwork-skill
```

The [skills.sh](https://skills.sh) CLI installs into whichever agent directories
it finds, so this works outside Claude Code and Codex too.

### Local install (Claude Code or Codex)

```bash
git clone https://github.com/dbhq-uk/deskwork-skill.git
cd deskwork-skill
./install.sh          # Claude Code: symlinks into ~/.claude/skills (edits are live)
./install-codex.sh    # Codex: installs into ~/.codex/skills
```

[`install.sh`](install.sh) and [`install-codex.sh`](install-codex.sh) are the
same install two ways: Claude Code substitutes `${CLAUDE_SKILL_DIR}`, so the
whole skill directory is symlinked untouched, while Codex does not, so its
`SKILL.md` is rewritten at install time. Re-run the Codex one after editing
`SKILL.md`.

## Requirements

Python 3.11 or later, standard library only. `git`, and `gh` 2.94 or later,
authenticated - every verb here reads or writes GitHub issues. Both installers
and every mode refuse an older `gh`.

## Opt in, per repository

deskwork does nothing at all until a repository has a `.github/deskwork.toml` saying `enabled = true`. Write a starter, which ships switched off:

```bash
python3 ~/.claude/skills/deskwork/scripts/deskwork.py init
```

Edit it, set `enabled = true`, commit it, and run `init` again to create the labels. The starter is [`skills/deskwork/deskwork.toml.example`](skills/deskwork/deskwork.toml.example).

## The modes

All require the working directory to be inside a git repository with `deskwork.toml` present and `enabled = true`. Any directory in the repository works, including a subdirectory or a git worktree. Issues go to the repository the `origin` remote points at.

### capture - file a new issue

```bash
python3 ~/.claude/skills/deskwork/scripts/deskwork.py capture --template --type Bug > body.md
# fill in every section, then:
python3 ~/.claude/skills/deskwork/scripts/deskwork.py capture \
  --title "Retry logic drops the last attempt" \
  --type Bug \
  --area infra \
  --body-file body.md
```

Refuses a body that leaves out a section its type needs or still says `_not stated_`. Before filing, it compares the title with every open issue and asks GitHub's hybrid search, which also sees issues closed in the last 30 days. If anything looks like the same issue, it files nothing and prints the candidates (exit 10); `--file` files anyway. Otherwise it files with `gh issue create`, applies the Triage label and the area label, reads the issue back, and with a board configured puts it on the board with Status set to Triage.

### review - reconcile the dependency graph

```bash
python3 ~/.claude/skills/deskwork/scripts/deskwork.py review --json
```

Reads every open issue in one query and prints the graph: each issue's blockers with their state, whether it is still in Triage, what a human already decided about its edges, and any cycles and bottlenecks. It writes nothing. An agent reasons about what should block what; you approve or reject each proposal; then one of four verbs records your answer:

```bash
deskwork.py link 12 --blocked-by 5 --reason "The migration needs the schema"
deskwork.py unlink 12 --blocked-by 5 --reason "No longer needed"
deskwork.py reject 12 --blocked-by 5 --reason "Different areas"
deskwork.py keep 12 --blocked-by 5 --reason "Order matters here"
```

`link` and `unlink` write through `gh issue edit` and read the edge back. All four record the decision and its reason in one comment on the issue, so a rejected edge is not proposed again.

### roadmap - write the order, with reasons

```bash
python3 ~/.claude/skills/deskwork/scripts/deskwork.py roadmap --order order.json
```

Takes the order an agent reasoned, as a list of `{"ref": "#7", "reason": "..."}`, and checks it against the live graph. An entry that is closed, still in Triage or blocked is refused by name, and nothing is written. Otherwise it writes `roadmap.md` with the reason under each item under `## Next`, lists what is blocked, ready but not ordered, and still in Triage, and commits the file alone.

### init - opt in and set up

```bash
python3 ~/.claude/skills/deskwork/scripts/deskwork.py init
```

With no config, writes the starter switched off. With one, creates the labels `capture` applies and, with a board, adds the Triage option to Status while keeping every existing option. Reports only what it created.

### intake - put existing issues on the board

```bash
python3 ~/.claude/skills/deskwork/scripts/deskwork.py intake
```

Adds every open issue that is not on the board, for a repository with a board and issues from before deskwork.

### doctor - report drift

```bash
python3 ~/.claude/skills/deskwork/scripts/deskwork.py doctor
```

Reports labels in the config and not the repository, `area:` labels in the repository and not the config, issue types not enabled, and with a board, a missing Triage option and open issues not on it. Exits 1 on any drift.

## The config file

`.github/deskwork.toml`. TOML, not YAML, so that no extra packages are needed.

```toml
enabled = true
roadmap = "roadmap.md"
designs = "docs/designs/"
issue_types = ["Bug", "Feature", "Task"]
triage_label = "triage"

[labels]
area = ["infra", "docs"]

# Optional
# project = "PVT_kwDOABCD1234"
# triage_status = "Triage"
```

The board is optional. Without it, the Triage label alone marks what is unreviewed. With it, the project is stored by node ID, not title: titles are not unique, and an unlinked project can conflict with a linked one.

`enabled = true` is required. File presence alone does not arm the skill.

## Testing

The config parser, graph construction, cycle detection, bottleneck finding and roadmap rendering are tested without touching GitHub. Every mode also runs end to end against a fake `gh` that keeps a small GitHub in a file and changes it on every write, so a test can check the write, the read-back and what GitHub would hold afterwards.

```bash
python3 -m pytest skills/deskwork/tests -q
```

The fixtures deliberately include the cases most likely to produce plausible wrong answers: a cross-repository dependency edge, an issue blocking three others, an issue whose blocker has closed, a Triage issue that is also blocked, a cycle in the graph, and a link that GitHub reports as written but that landed on a different issue.

**Honesty note:** No mode has yet been run against a live Projects v2 board. Every mode is tested against the fake `gh`; none has had a supervised run on a real repository and board. A first deployment should begin with `init` on a test repository and a human watching the board.

## What it does not do

- **It does not close issues.** A pull request can carry `Closes #N`; GitHub closes it when a human merges.
- **It does not touch pull requests.** It neither merges nor proposes a merge order. [`buildwork`](https://github.com/dbhq-uk/buildwork-skill) proposes one; a human merges.
- **It does not infer dependency edges.** An edge exists because it was proposed and accepted. The reasoning is recorded with it.
- **It holds no credentials.** `gh auth` is the credential. deskwork stores no token and keeps no `~/.dbhq/deskwork/`, so there is nothing of its own to leak.
- **It does not run on a schedule.** Every pass is on demand.

## Constraints

Eight things that must not break. See [AGENTS.md](AGENTS.md).

## The pair

deskwork decides what the work is and what order it goes in. [`buildwork`](https://github.com/dbhq-uk/buildwork-skill) runs it - one agent per issue, each in its own worktree, collecting the results and proposing a merge order.

Neither needs the other. buildwork reads issues and a roadmap file whoever wrote them, and falls back to open issues in no particular order while saying so.

## Also from DBHQ

Every DBHQ agent skill is free, open source and installable from the same
marketplace, and all of them are documented at
**[skills.dbhq.uk](https://skills.dbhq.uk)**. The marketplace itself is
[dbhq-uk/marketplace](https://github.com/dbhq-uk/marketplace) - one
`/plugin marketplace add` and every one of them is available.

| Skill | What it does |
|---|---|
| [outlook](https://skills.dbhq.uk/outlook/) | Microsoft 365 mail and calendar, from the terminal |
| [trello](https://skills.dbhq.uk/trello/) | Your boards, run from your agent |
| [legwork](https://skills.dbhq.uk/legwork/) | Research that settles a decision, and says when it cannot |
| [dovetail](https://skills.dbhq.uk/dovetail/) | Checks whether your repository still agrees with itself |
| [verve](https://skills.dbhq.uk/verve/) | Strips AI tells from prose and puts a voice back |
| [vela](https://skills.dbhq.uk/vela/) | Compiler-exact code search, in any language you index |
| [garmin](https://skills.dbhq.uk/garmin/) | Your Garmin data, answered in the terminal |
| [imager](https://skills.dbhq.uk/imager/) | Images from GPT Image 2, costed before it spends |
| [gitview](https://skills.dbhq.uk/gitview/) | Which branches are finished, and safe to delete |
| [atlassian](https://skills.dbhq.uk/atlassian/) | Jira issues and Confluence pages |
| [pennyblack](https://skills.dbhq.uk/pennyblack/) | A physical letter, posted from the terminal |
| [buildwork](https://skills.dbhq.uk/buildwork/) | Your open issues, run as parallel agents |
| [groupwork](https://skills.dbhq.uk/groupwork/) | A second agent on the work, adversary or partner |
| [headwork](https://skills.dbhq.uk/headwork/) | One decision at a time, with a recommendation |

Plus [heliograph](https://skills.dbhq.uk/heliograph/), for a machine you cannot log into.

## Licence

MIT. See [LICENSE](LICENSE).
