# The graph and the roadmap

Read this before proposing edges or writing a roadmap.

## Who does what

- **The script** reads the graph and prints it. Later, it writes one approved
  decision at a time, reads it back, and records the reason on the issue.
- **The agent** reasons about what should block what, citing the issues and
  what the human is trying to get done.
- **The human** approves or rejects each proposal, and has the final say on
  precedence.

Nothing is inferred into the graph. An edge exists because it was proposed
and accepted, and its reason is recorded with it.

## The flow

1. Run `review --json`.
2. Read every open issue and any design file it links to.
3. Reason about what blocks what.
4. Show the proposed additions and removals, with a reason for each, and wait
   for the human's answer.
5. Record each answer with one verb. Never write an edge any other way.

## What review --json holds

For each open issue: its number and title, type, labels, parent, whether it
is in Triage, every blocker with its state (`OPEN` or `CLOSED`) and title, and
the decisions already recorded about its edges. Then the lists `ready`,
`blocked` and `triage`, the `cycles`, and the `bottlenecks` (any issue that
blocks three or more). A closed blocker blocks nothing, and a Triage issue is
neither ready nor blocked.

## The four verbs

| The human | Verb | Graph | Remembered as |
|---|---|---|---|
| approves adding "12 is blocked by 5" | `link 12 --blocked-by 5 --reason "..."` | edge added | `linked` |
| approves removing it | `unlink 12 --blocked-by 5 --reason "..."` | edge removed | `unlinked` |
| rejects adding it | `reject 12 --blocked-by 5 --reason "..."` | unchanged | `rejected` |
| rejects removing it | `keep 12 --blocked-by 5 --reason "..."` | unchanged | `deliberate` |

`--reason` is required. The blocker may be in another repository:
`--blocked-by owner/repo#9`. `link` and `unlink` write through
`gh issue edit` and read the edge list back. If GitHub shows anything other
than what was asked for, the verb exits 4 and names the edge that is there,
with the command that removes it. Run that command only with the human's
agreement.

## Memory

Each decision is one line in a single comment on the issue, marked
`<!-- deskwork -->` and edited in place, never duplicated. A later decision
about the same edge replaces the earlier one. Lines a person writes in that
comment are kept as they are.

Do not propose adding an edge remembered as `rejected` or `unlinked`. Do not
propose removing one remembered as `deliberate`. If circumstances have
changed, say so and ask; do not quietly propose it again.

## The roadmap

The order under `## Next` is the agent's reasoning, approved by the human,
not something the script computes. Write it as a JSON list, first thing first:

```json
[{"ref": "#7", "reason": "Unblocks the migration and the reports"},
 {"ref": "#6", "reason": "Free now that its blocker has closed"}]
```

Then `roadmap --order order.json`, or `--order -` to read it from stdin.
The whole order is refused, each problem named, if any entry is closed, in
Triage, blocked by an open issue, in another repository, listed twice, or has
no reason. Otherwise `roadmap.md` is written at the repository root and
committed on its own, with nothing else that happens to be staged.

The file's sections:

- `## Next` - the order, exactly as given, with `Why:` and the reason under
  each item. buildwork runs these.
- `## Blocked` - open issues waiting on an open blocker, each with its
  blockers.
- `## Later` - ready, and not ordered this time. buildwork holds these.
- `## Cycles` and `## Bottlenecks` - when there are any.
- `## Triage` - filed and not yet reviewed. Listed, never ordered.

To change the order, change the reasoning and write it again. To change what
is blocked, change the edges with the verbs.
