"""Issue numbers and database IDs are different things that look the same.

The dependencies API takes a database ID and will happily accept an issue
number, linking to a different issue in a different repository and returning
201. Nothing downstream notices. So the two are distinct types here, and the
only way to get an IssueId is to ask GitHub for it.
"""
from dataclasses import dataclass

import gh


class IssueNumber(int):
    """What you see in the UI and write as #144."""


class IssueId(int):
    """The internal database id. What every dependencies call actually wants.

    Never construct this by wrapping an IssueNumber or a bare int read from
    a variable or response field. The only sanctioned sources are resolve()
    and the id field of a GitHub API response.
    """


class NodeId(str):
    """The GraphQL node id. What every Projects v2 mutation actually wants.

    Never construct this by wrapping a bare string read from a variable or
    response field. The only sanctioned source is node_id() and the node_id
    field of a GitHub API response.
    """


class MismatchedIssue(Exception):
    """GitHub returned an issue that is not the one that was asked for."""


@dataclass(frozen=True)
class Ref:
    owner: str
    repo: str
    number: IssueNumber

    def __str__(self):
        return f"{self.owner}/{self.repo}#{int(self.number)}"


def require_id(value):
    """Guard for every function that writes a dependency."""
    if not isinstance(value, IssueId):
        raise TypeError(
            f"expected an IssueId (the database id), got {type(value).__name__} "
            f"{int(value)}. Resolve it with ids.resolve() first."
        )
    return int(value)


def require_node_id(value):
    """Guard for every function that calls a Projects v2 mutation."""
    if not isinstance(value, NodeId):
        raise TypeError(
            f"expected a NodeId (the GraphQL node id), got {type(value).__name__} "
            f"{value}. Fetch it with ids.node_id() first."
        )
    return str(value)


def resolve(ref):
    """Turn an issue number into its database id, checking what came back."""
    issue = gh.api(f"repos/{ref.owner}/{ref.repo}/issues/{int(ref.number)}")
    if issue["number"] != int(ref.number):
        raise MismatchedIssue(
            f"asked for {ref}, GitHub returned number {issue['number']}"
        )
    return IssueId(issue["id"])


def node_id(ref):
    """Turn an issue number into its GraphQL node id, checking what came back."""
    issue = gh.api(f"repos/{ref.owner}/{ref.repo}/issues/{int(ref.number)}")
    if issue["number"] != int(ref.number):
        raise MismatchedIssue(
            f"asked for {ref}, GitHub returned number {issue['number']}"
        )
    return NodeId(issue["node_id"])
