"""What a human already decided about an issue's edges, kept on the issue.

Without this, every review pass re-proposes the same rejected edge, you learn
to skim the list, and a bad edge gets waved through.

One comment per issue carries it, marked <!-- deskwork --> and edited in
place. Each line is one decision about one edge "this issue is blocked by X":

    - linked: owner/repo#12 reason       a human approved adding it
    - unlinked: owner/repo#12 reason     a human approved removing it
    - rejected: owner/repo#12 reason     a human rejected adding it
    - deliberate: owner/repo#12 reason   a human rejected removing it

A later decision about the same edge replaces the earlier one. Any line that
is not one of these is kept exactly as it was, so a person can write in the
comment without deskwork eating it.
"""
import re
from dataclasses import dataclass, field

import gh
import ids

MARKER = "<!-- deskwork -->"
KINDS = ("linked", "unlinked", "rejected", "deliberate")
PREAMBLE = "**deskwork** is remembering these decisions, so it stops asking."
UNPARSEABLE_HEADER = "**The following lines were not recognised - keeping them unchanged:**"
_LINE = re.compile(
    r"^- (linked|unlinked|rejected|deliberate): ([\w.-]+)/([\w.-]+)#(\d+)(.*)$"
)


class WriteNotConfirmed(Exception):
    """The comment was written and does not read back as it should."""


@dataclass
class Memory:
    decisions: dict = field(default_factory=dict)  # Ref -> (kind, note)
    unparseable_lines: list = field(default_factory=list)

    def record(self, kind, ref, note=""):
        if kind not in KINDS:
            raise ValueError(f"unknown decision {kind!r}")
        self.decisions[ref] = (kind, " ".join(str(note).split()))

    def of(self, kind):
        return {ref for ref, (k, _) in self.decisions.items() if k == kind}

    @property
    def rejected_additions(self):
        return self.of("rejected")

    @property
    def deliberate_edges(self):
        return self.of("deliberate")


def parse(body):
    result = Memory()
    if not body or MARKER not in body:
        return result
    for line in body.split(MARKER, 1)[1].split("\n"):
        if not line.strip() or line in (PREAMBLE, UNPARSEABLE_HEADER):
            continue
        match = _LINE.match(line)
        if match:
            kind, owner, repo, number, note = match.groups()
            ref = ids.Ref(owner, repo, ids.IssueNumber(int(number)))
            result.decisions[ref] = (kind, note.strip())
        else:
            result.unparseable_lines.append(line)
    return result


def render(mem):
    lines = [MARKER, "", PREAMBLE, ""]
    for kind in KINDS:
        for ref in sorted(mem.of(kind), key=str):
            note = mem.decisions[ref][1]
            lines.append(f"- {kind}: {ref} {note}".rstrip())
    if mem.unparseable_lines:
        lines.append("")
        lines.append(UNPARSEABLE_HEADER)
        lines.extend(mem.unparseable_lines)
    return "\n".join(lines)


def as_json(mem, home):
    return [
        {"decision": kind, "ref": ref.short(home), "note": note}
        for ref, (kind, note) in sorted(mem.decisions.items(), key=lambda item: str(item[0]))
    ]


def find_comment(ref):
    """The marker comment on ref, however many comments come before it."""
    pages = gh.api(
        f"repos/{ref.owner}/{ref.repo}/issues/{int(ref.number)}/comments",
        extra_args=["--paginate", "--slurp"],
    ) or []
    for page in pages:
        for comment in page if isinstance(page, list) else [page]:
            if MARKER in (comment.get("body") or ""):
                return comment
    return None


def read(ref):
    comment = find_comment(ref)
    return parse(comment["body"] if comment else "")


def _write(ref, mem, comment):
    """Write the memory comment, in place if it exists, then read it back."""
    body = {"body": render(mem)}
    if comment:
        written = gh.api(
            f"repos/{ref.owner}/{ref.repo}/issues/comments/{comment['id']}",
            method="PATCH", body=body,
        )
    else:
        written = gh.api(
            f"repos/{ref.owner}/{ref.repo}/issues/{int(ref.number)}/comments",
            method="POST", body=body,
        )
    comment_id = (written or {}).get("id") or (comment or {}).get("id")
    back = gh.api(f"repos/{ref.owner}/{ref.repo}/issues/comments/{comment_id}") if comment_id else None
    if not back or parse(back.get("body", "")).decisions != mem.decisions:
        raise WriteNotConfirmed(
            f"the deskwork comment on {ref} does not read back as written. "
            "Check it by hand before recording anything else."
        )


def record(ref, kind, blocker, note):
    """Record one decision about the edge "ref is blocked by blocker"."""
    comment = find_comment(ref)
    mem = parse(comment["body"] if comment else "")
    mem.record(kind, blocker, note)
    _write(ref, mem, comment)
    return mem
