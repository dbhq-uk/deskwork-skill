# The shape of an issue

Read this before running `capture`. It is what makes an issue worth filing,
rather than noise a later agent has to unpick.

## Research before you write

Read the files the issue is about, the tests that cover them, and recent
commits for the area, before writing a word of the body. An issue written
from a hunch reads like one - vague context, acceptance criteria that just
restate the title, a fix that turns out to already exist two commits back.
Cite what you found: a file path, a test name, a commit.

## Acceptance criteria are checkable statements, not intentions

Whoever works the issue later - often an agent - reads it literally. It does
not infer intent the way a person skimming a backlog would. "Retries should
be more reliable" gives nothing to check against. "A dropped connection on
the third attempt is retried, and a test covers it" does: it names a
condition and a proof.

Write every acceptance line as something that is true or false once the work
is done, not a direction to head in.

## Every section, filled

`capture --template --type Bug` prints the sections a Bug needs: Context,
Expected, Actual and Acceptance. A Feature has Context, Proposal, Acceptance
and Out of scope. A Task has Context and Acceptance. `capture` refuses a body
that leaves one out or still says `_not stated_`. If a section genuinely has
nothing in it, say why in a sentence rather than leaving the placeholder.

## A design goes to a file, never into the body

If the change needs a design - more than a paragraph of reasoning, a
sequence of steps, a diagram - write it to a file in the repository and link
to it from Context or Proposal. Never paste a design into the issue body
itself. A file is versioned and diffable and can be read on its own; an
issue body is a summary with a pointer in it.

## Titles

Under 72 characters, and no `[Bug]`, `[Feature]` or similar prefix - the
issue type already carries that. A prefix in the title just repeats the type,
and the two drift the moment someone edits one and not the other.

For example, `owner/repo#123` titled "Retry logic drops the last attempt on
a dropped connection", type `Bug` - not "[Bug] Retry logic drops the last
attempt".

## When capture finds a possible duplicate

`capture` checks before it files: the title against every open issue, and
GitHub's hybrid search, which also sees issues closed in the last 30 days.
When it finds candidates it files nothing and exits 10. A near-duplicate is a
reason to comment on the existing issue instead. A weak or unrelated match is
a reason to run the same command again with `--file`. Say which it was.
