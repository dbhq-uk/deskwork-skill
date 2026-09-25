"""The identifiers one issue carries, kept apart.

An issue has a number (#144), which people and gh use, and a GraphQL node id
("I_kwDOAbc123"), which Projects v2 mutations want. The REST dependencies API
also takes a database id, and will link a different issue in a different
repository if it is given a number instead, returning 201 as it does. deskwork
no longer uses that API: edges are written with gh issue edit, which takes the
number and resolves it itself. So there is no database id type here, and no
function that produces one.
"""
import re
from dataclasses import dataclass

import gh


class IssueNumber(int):
    """What you see in the UI and write as #144."""


class NodeId(str):
    """The GraphQL node id. What every Projects v2 mutation wants.

    Never construct this by wrapping a bare string read from a variable. The
    only sanctioned source is node_id(), which checks what GitHub returned.
    """


class MismatchedIssue(Exception):
    """GitHub returned an issue that is not the one that was asked for."""


_URL = re.compile(r"^https?://[^/]+/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)/(?:issues|pull)/(?P<n>\d+)/?$")
_QUALIFIED = re.compile(r"^(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)#(?P<n>\d+)$")
_LOCAL = re.compile(r"^#?(?P<n>\d+)$")


@dataclass(frozen=True)
class Ref:
    owner: str
    repo: str
    number: IssueNumber

    def __str__(self):
        return f"{self.owner}/{self.repo}#{int(self.number)}"

    @property
    def repo_arg(self):
        """The -R argument gh wants for this issue's repository."""
        return f"{self.owner}/{self.repo}"

    def short(self, home):
        """#N in the home repository, owner/repo#N anywhere else."""
        if (self.owner, self.repo) == tuple(home):
            return f"#{int(self.number)}"
        return str(self)

    def gh_arg(self, home):
        """How gh issue edit names this issue from the home repository.

        A number inside the home repository, a URL outside it, because gh
        reads a bare number as an issue in the repository given by -R.
        """
        if (self.owner, self.repo) == tuple(home):
            return str(int(self.number))
        return f"https://github.com/{self.owner}/{self.repo}/issues/{int(self.number)}"


def parse(text, home):
    """A Ref from 12, "#12", "owner/repo#12" or an issue URL."""
    text = str(text).strip()
    for pattern in (_LOCAL, _QUALIFIED, _URL):
        match = pattern.match(text)
        if match:
            owner = match.groupdict().get("owner") or home[0]
            repo = match.groupdict().get("repo") or home[1]
            return Ref(owner, repo, IssueNumber(int(match.group("n"))))
    raise ValueError(f"not an issue reference: {text!r}. Use 12, #12, owner/repo#12 or an issue URL")


def from_url(url):
    match = _URL.match(url or "")
    if not match:
        raise ValueError(f"not an issue URL: {url!r}")
    return Ref(match.group("owner"), match.group("repo"), IssueNumber(int(match.group("n"))))


def require_node_id(value):
    """Guard for every function that calls a Projects v2 mutation."""
    if not isinstance(value, NodeId):
        raise TypeError(
            f"expected a NodeId (the GraphQL node id), got {type(value).__name__} "
            f"{value}. Fetch it with ids.node_id() first."
        )
    return str(value)


def node_id(ref):
    """Turn an issue number into its GraphQL node id, checking what came back."""
    issue = gh.run_json(
        ["issue", "view", str(int(ref.number)), "-R", ref.repo_arg, "--json", "id,number"]
    )
    if issue["number"] != int(ref.number):
        raise MismatchedIssue(f"asked for {ref}, GitHub returned number {issue['number']}")
    return NodeId(issue["id"])
