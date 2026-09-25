# Boards (Projects v2)

A board is optional. Without one, deskwork works from labels alone: every
issue it files carries the Triage label, and that label is what keeps it out
of the roadmap until a human has reviewed it. With `project` set in the
config, `capture` also adds each new issue to the board and sets Status to
Triage, and `roadmap` treats Status Triage the same as the label.

## Identifiers

One GitHub issue carries several identifiers and none of them is interchangeable:

| Identifier | Looks like | Used by |
|---|---|---|
| Issue number | `144` | humans, URLs, `gh issue` commands |
| Database id | `3527190001` | the REST dependencies API, which deskwork does not use |
| GraphQL node id | `I_kwDOAbc123` | adding the issue to a board |
| Project item id | `PVTI_lADOABCD1234` | setting a field on the issue's place on one board |

Dependency edges go through `gh issue edit --add-blocked-by` and `--remove-blocked-by`, which take the issue number and resolve it inside gh. The REST dependencies API takes a database id, links a different issue when handed a number, and still returns 201, so deskwork never calls it.

Setting Status wants the project item id that adding the issue returned, not the issue's node id. Sending the node id fails after the issue already exists, which is how a retry used to file the same issue twice. deskwork keeps the item id, and checks the Status it set by reading it back.

## A board is addressed by node id

Always by node id, never by title. Titles are not unique, and a project need
not be linked to the repository, so `--add-project` by title can silently add
to the wrong one of two same-named boards. Find the id with:

```bash
gh project list --owner OWNER --format json
```

## What init changes on a board

One thing: it adds the Triage option to the built-in Status field if it is
missing. GitHub replaces the whole option list on that update, so init sends
every existing option back with its id, colour and description, read
immediately before, and afterwards checks that every one of them is still
there. No item loses its status. deskwork creates no other fields; Effort and
Risk are GitHub issue fields now, set on the issue rather than on a board.

## The project scope

Board work needs the `project` scope, separate from `repo`:

```bash
gh auth refresh -s project
```

Without it, every mode that touches the board says so and names that command,
and `doctor` exits 1.
