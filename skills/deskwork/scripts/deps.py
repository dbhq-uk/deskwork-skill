"""Dependency edges: written with gh issue edit, then read back from GitHub.

gh takes the issue number (or, across repositories, the URL) and resolves it
itself, so no database id is handled here. That removes the hazard the old
REST path carried, where a number sent as an id linked a different issue and
GitHub still returned 201.

A write that gh reports as successful is still not trusted. The edge list is
read back, and if it does not show what was asked for, WriteNotConfirmed names
whatever edge appeared or went instead, with the command that undoes it.
"""
from dataclasses import dataclass

import gh
import ids


class WriteNotConfirmed(Exception):
    """gh reported success and GitHub does not show the edge as asked."""


@dataclass(frozen=True)
class Blocker:
    ref: ids.Ref
    state: str  # OPEN or CLOSED
    title: str


def blocked_by(ref):
    """Every issue blocking ref, open and closed, with its state."""
    data = gh.run_json(
        ["issue", "view", str(int(ref.number)), "-R", ref.repo_arg, "--json", "number,blockedBy"]
    )
    if data["number"] != int(ref.number):
        raise ids.MismatchedIssue(f"asked for {ref}, GitHub returned number {data['number']}")
    connection = data.get("blockedBy") or {}
    nodes = connection.get("nodes") or []
    total = connection.get("totalCount", len(nodes))
    if total != len(nodes):
        raise WriteNotConfirmed(
            f"{ref} has {total} blockers and gh returned {len(nodes)}. "
            "Refusing to act on a partial list."
        )
    return [
        Blocker(ids.from_url(node["url"]), node.get("state", "OPEN"), node.get("title", ""))
        for node in nodes
    ]


def _refs(blockers):
    return {b.ref for b in blockers}


def _edit(ref, flag, blocker):
    home = (ref.owner, ref.repo)
    return ["issue", "edit", str(int(ref.number)), "-R", ref.repo_arg, flag, blocker.gh_arg(home)]


def _command(args):
    return "gh " + " ".join(args)


def link(ref, blocker):
    """Make ref blocked by blocker. Returns False if the edge was already there."""
    before = _refs(blocked_by(ref))
    if blocker in before:
        return False
    gh.run(_edit(ref, "--add-blocked-by", blocker), write=True)
    after = _refs(blocked_by(ref))
    if blocker in after and after - before == {blocker}:
        return True
    problems = []
    if blocker not in after:
        problems.append(f"{ref} should now be blocked by {blocker} and is not.")
    for stray in sorted(after - before - {blocker}, key=str):
        problems.append(
            f"{ref} is now blocked by {stray}, which was not asked for. "
            f"Remove it with: {_command(_edit(ref, '--remove-blocked-by', stray))}"
        )
    raise WriteNotConfirmed(" ".join(problems))


def unlink(ref, blocker):
    """Stop ref being blocked by blocker. Returns False if there was no such edge."""
    before = _refs(blocked_by(ref))
    if blocker not in before:
        return False
    gh.run(_edit(ref, "--remove-blocked-by", blocker), write=True)
    after = _refs(blocked_by(ref))
    if blocker not in after and before - after == {blocker}:
        return True
    problems = []
    if blocker in after:
        problems.append(f"{ref} should no longer be blocked by {blocker} and still is.")
    for lost in sorted(before - after - {blocker}, key=str):
        problems.append(
            f"{ref} is no longer blocked by {lost}, which was not asked for. "
            f"Put it back with: {_command(_edit(ref, '--add-blocked-by', lost))}"
        )
    for stray in sorted(after - before, key=str):
        problems.append(
            f"{ref} is now blocked by {stray}, which was not asked for. "
            f"Remove it with: {_command(_edit(ref, '--remove-blocked-by', stray))}"
        )
    raise WriteNotConfirmed(" ".join(problems))
