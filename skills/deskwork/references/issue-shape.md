# The shape of an issue

Read this before calling `issues.create`. It is what makes an issue worth
filing, rather than noise a later agent has to unpick.

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

## A design goes to a file, never into the body

If the change needs a design - more than a paragraph of reasoning, a
sequence of steps, a diagram - write it to a file in the repository and link
to it from the issue, in the `context` or `proposal` section passed to
`body_for`. Never paste a design into the issue body itself. A file is
versioned and diffable and can be read on its own; an issue body is a
summary with a pointer in it.

## Titles

Under 72 characters, and no `[Bug]`, `[Feature]` or similar prefix - the
issue type already carries that. `org_issue_types` lists what an
organisation has enabled (`Bug`, `Feature`, `Task` and so on), and `create`
takes it as `issue_type`. A prefix in the title just repeats the type field,
and the two drift the moment someone edits one and not the other.

For example, `owner/repo#123` titled "Retry logic drops the last attempt on
a dropped connection", type `Bug` - not "[Bug] Retry logic drops the last
attempt".

## Check what is already there before filing

`search_similar(owner, repo, title)` runs a cheap lexical search over open
issues and is shown to a human before `create` runs. It is advisory only -
it never blocks a create and nothing merges on its say-so. A near-duplicate
in the results is a reason to comment on the existing issue instead of
filing a new one; a weak or unrelated match is a reason to file anyway.
