# Security

## Reporting a vulnerability

Email <dan@dbhq.uk> rather than opening a public issue. Include what you found,
how to reproduce it, and what an attacker could do with it. You will get a first
response within 48 hours.

## What this skill does

deskwork files GitHub issues, records which issue blocks which, and writes a
roadmap file into the repository. The scripts do the deterministic half; the
agent following `SKILL.md` does the reasoning, and a human approves each
dependency before it is written.

### Credentials

**None are handled, stored or read.** `gh auth` is the credential and `gh`
holds it. There is no token file, no environment variable, no keyring entry and
no `~/.dbhq/deskwork/`. Board work needs the `project` scope on that token;
everything else needs only what `gh issue` needs.

### Network

**Only through `gh`.** Every call to GitHub goes through `gh.py`, which runs
`gh issue`, `gh label`, `gh repo view` and `gh api` (REST and GraphQL). The
scripts never open a socket themselves. `git` is run only locally: nothing is
fetched, pulled or pushed.

### What it writes on GitHub

Only in a repository whose `.github/deskwork.toml` says `enabled = true`:

- New issues, from `capture`, with the Triage label, and optionally an
  `area:` label, an issue type, a parent and a blocking issue.
- Labels, from `init`: the Triage label and one `area:` label per configured
  area.
- Dependency edges, from `link` and `unlink`, one at a time with
  `gh issue edit --add-blocked-by` or `--remove-blocked-by`, each read back.
- One comment per issue, marked `<!-- deskwork -->` and edited in place, that
  records what a human decided about its edges.
- With a board configured: issues added to it with Status set to Triage, and
  the Triage option added to the Status field. Every existing option is re-read
  immediately before that write and checked afterwards.

It never closes, deletes or transfers an issue. `gh.py` refuses such a call
before `gh` starts: `gh issue close`, `delete` or `transfer`, any `DELETE`, a
write carrying `state`, and the `closeIssue`, `deleteIssue`, `transferIssue`
and `updateIssue` mutations. It never touches a pull request, and it deletes
nothing on a board.

### What it writes in your repository

- `.github/deskwork.toml`, from `init`, only when the file does not exist, and
  always with `enabled = false`.
- The roadmap file the config names, from `roadmap`, committed alone in a local
  commit. The commit is checked afterwards to hold that one file. Nothing is
  pushed. A `roadmap` or `designs` path that is absolute or leads outside the
  repository is refused when the config is read, before anything is written.

`--dry-run` on any mode that writes prints what it would do and writes nothing.

### Command execution

Only `gh` and `git`, each with an argument list and never through a shell.
Nothing from the config file or from an issue is run as a command.

## Supply chain

Python standard library only. No PyPI packages, no `requirements.txt`, no venv
and no lockfile, which is why Dependabot here watches GitHub Actions and
nothing else. The two runtime dependencies are `git` and `gh` 2.94 or later,
both of which you installed.
