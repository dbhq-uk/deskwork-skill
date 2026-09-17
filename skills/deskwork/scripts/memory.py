"""What a human already decided, kept on the issue.

Without this, every review pass re-proposes the same rejected edge, you learn
to skim the list, and a bad edge gets waved through.
"""
import re
from dataclasses import dataclass, field

import gh
import ids

MARKER = "<!-- deskwork -->"
_LINE = re.compile(r"^- (rejected|deliberate): ([\w.-]+)/([\w.-]+)#(\d+)(.*)$", re.M)


@dataclass
class Memory:
    rejected_additions: set = field(default_factory=set)
    deliberate_edges: set = field(default_factory=set)
    _notes: dict = field(default_factory=dict)
    unparseable_lines: list = field(default_factory=list)


def parse(body):
    result = Memory()
    if not body or MARKER not in body:
        return result

    # Split at the marker to find the deskwork section
    parts = body.split(MARKER, 1)
    if len(parts) < 2:
        return result

    section_text = parts[1]
    lines = section_text.split('\n')

    # Lines to skip: the generated preamble and section headers
    PREAMBLE = "**deskwork** is remembering these decisions, so it stops asking."
    UNPARSEABLE_HEADER = "**The following lines were not recognised - keeping them unchanged:**"

    for line in lines:
        if not line.strip():
            # Skip blank lines
            continue

        if line == PREAMBLE or line == UNPARSEABLE_HEADER:
            # Skip generated headers
            continue

        # Try to match the pattern
        match = _LINE.match(line)
        if match:
            kind, owner, repo, number, note = match.groups()
            ref = ids.Ref(owner, repo, ids.IssueNumber(int(number)))
            note = note.strip()
            if kind == "rejected":
                result.rejected_additions.add(ref)
            else:
                result.deliberate_edges.add(ref)
            if note:
                result._notes[ref] = note
        else:
            # Any line that doesn't match the pattern and isn't generated is preserved
            result.unparseable_lines.append(line)

    return result


def render(mem):
    lines = [MARKER, "", "**deskwork** is remembering these decisions, so it stops asking.", ""]
    for ref in sorted(mem.rejected_additions, key=str):
        line = f"- rejected: {ref}"
        if ref in mem._notes:
            line += f" {mem._notes[ref]}"
        lines.append(line)
    for ref in sorted(mem.deliberate_edges, key=str):
        line = f"- deliberate: {ref}"
        if ref in mem._notes:
            line += f" {mem._notes[ref]}"
        lines.append(line)

    # Preserve unparseable lines verbatim
    if mem.unparseable_lines:
        lines.append("")
        lines.append("**The following lines were not recognised - keeping them unchanged:**")
        lines.extend(mem.unparseable_lines)

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
