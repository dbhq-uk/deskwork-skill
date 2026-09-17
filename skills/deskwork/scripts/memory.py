"""What a human already decided, kept on the issue.

Without this, every review pass re-proposes the same rejected edge, you learn
to skim the list, and a bad edge gets waved through.
"""
import re
from dataclasses import dataclass, field

import gh
import ids

MARKER = "<!-- deskwork -->"
_LINE = re.compile(r"^- (rejected|deliberate): ([\w.-]+)/([\w.-]+)#(\d+)$", re.M)


@dataclass
class Memory:
    rejected_additions: set = field(default_factory=set)
    deliberate_edges: set = field(default_factory=set)


def parse(body):
    result = Memory()
    if not body or MARKER not in body:
        return result
    for kind, owner, repo, number in _LINE.findall(body):
        ref = ids.Ref(owner, repo, ids.IssueNumber(int(number)))
        if kind == "rejected":
            result.rejected_additions.add(ref)
        else:
            result.deliberate_edges.add(ref)
    return result


def render(mem):
    lines = [MARKER, "", "**deskwork** is remembering these decisions, so it stops asking.", ""]
    for ref in sorted(mem.rejected_additions, key=str):
        lines.append(f"- rejected: {ref}")
    for ref in sorted(mem.deliberate_edges, key=str):
        lines.append(f"- deliberate: {ref}")
    return "\n".join(lines)


def _find_comment(ref):
    path = f"repos/{ref.owner}/{ref.repo}/issues/{int(ref.number)}/comments"
    for comment in gh.api(path) or []:
        if MARKER in (comment.get("body") or ""):
            return comment
    return None


def read(ref):
    comment = _find_comment(ref)
    return parse(comment["body"] if comment else "")


def _write(ref, mem):
    comment = _find_comment(ref)
    body = {"body": render(mem)}
    if comment:
        gh.api(f"repos/{ref.owner}/{ref.repo}/issues/comments/{comment['id']}",
               method="PATCH", body=body)
    else:
        gh.api(f"repos/{ref.owner}/{ref.repo}/issues/{int(ref.number)}/comments",
               method="POST", body=body)


def record_rejected_addition(ref, blocker):
    mem = read(ref)
    mem.rejected_additions.add(blocker)
    _write(ref, mem)


def record_deliberate_edge(ref, blocker):
    mem = read(ref)
    mem.deliberate_edges.add(blocker)
    _write(ref, mem)
