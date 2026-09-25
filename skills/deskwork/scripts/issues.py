"""Creating and finding issues.

gh issue create has no --type flag, so creation goes through the REST endpoint.
Issue types are the canonical GitHub categorisation; labels are the fallback
for an organisation that has not configured them.
"""
import urllib.parse
from dataclasses import dataclass, field

import deps
import gh
import ids
import memory

_SECTIONS = {
    "Bug": ["Context", "Expected", "Actual", "Acceptance"],
    "Feature": ["Context", "Proposal", "Acceptance", "Out of scope"],
    "Task": ["Context", "Acceptance"],
}

_ALIASES = {
    "expected": "Expected", "actual": "Actual", "context": "Context",
    "proposal": "Proposal", "acceptance": "Acceptance",
    "out_of_scope": "Out of scope",
}

# Words that carry no search signal, dropped regardless of length. A length
# cutoff - drop anything three characters or fewer - is backwards: it throws
# away exactly the words most likely to be distinctive (an acronym like CSP,
# an error code, a short proper noun) while keeping long but generic ones
# ("wrong", "about", "using"). This list drops only known filler, however
# long, and keeps everything else, however short.
_STOP_WORDS = frozenset({
    "a", "an", "the",
    "and", "or", "but", "nor", "so", "if", "than", "then",
    "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did",
    "has", "have", "had",
    "in", "on", "at", "by", "to", "of", "for", "with", "from", "as",
    "it", "its", "this", "that", "these", "those",
    "not", "no",
    "will", "can", "should", "would", "could",
})


def org_issue_types(org):
    query = (
        '{ organization(login:"%s"){ issueTypes(first:20)'
        "{ nodes{ name isEnabled } } } }" % org
    )
    data = gh.graphql(query)
    return [
        node["name"]
        for node in data["organization"]["issueTypes"]["nodes"]
        if node["isEnabled"]
    ]


def _search_terms(title):
    """Pick the words of a title worth searching on.

    Drop stop words, not short words - dropping by length is backwards, since
    it discards the acronyms and error codes a title is most likely to be
    distinctive by. If every word in the title turns out to be a stop word,
    fall back to the full word list rather than searching on nothing.
    """
    words = title.lower().split()
    kept = [word for word in words if word not in _STOP_WORDS]
    return kept or words


def search_similar(owner, repo, title):
    """Cheap lexical search. Shown to a human, never acted on automatically.

    Each term is percent-encoded before it is joined into the query string.
    A title is free text - an unescaped &, #, space or + in it would
    otherwise be read as a query separator, a URL fragment marker, a literal
    space, or an extra encoded space, corrupting the search rather than
    merely narrowing it.
    """
    terms = "+".join(
        urllib.parse.quote(word, safe="") for word in _search_terms(title)
    )
    path = f"search/issues?q=repo:{owner}/{repo}+is:issue+is:open+{terms}"
    return (gh.api(path) or {}).get("items", [])


def body_for(kind, **sections):
    lines = []
    wanted = _SECTIONS.get(kind, _SECTIONS["Task"])
    supplied = {_ALIASES.get(k, k): v for k, v in sections.items()}
    for heading in wanted:
        lines.append(f"**{heading}**")
        lines.append("")
        lines.append(supplied.get(heading, "_not stated_"))
        lines.append("")
    return "\n".join(lines).strip()


def create(owner, repo, title, body, issue_type, labels):
    payload = {"title": title, "body": body, "labels": list(labels)}
    if issue_type:
        payload["type"] = issue_type
    created = gh.api(f"repos/{owner}/{repo}/issues", method="POST", body=payload)
    return ids.Ref(owner, repo, ids.IssueNumber(created["number"]))


def list_open(owner, repo):
    """List all open issues in a repository, paginated and filtered.

    Returns a list of dicts with at least number, title, state, labels and
    node_id. Pull requests are filtered out (identified by the pull_request
    key). Pagination is handled transparently.
    """
    path = f"repos/{owner}/{repo}/issues"
    # Use --paginate --slurp to get all pages as a single array
    data = gh.api(path, extra_args=["--paginate", "--slurp"])
    if not data:
        return []

    # Flatten the pages array into a single list of issues
    issues_list = []
    for page in data:
        if isinstance(page, list):
            issues_list.extend(page)
        else:
            issues_list.append(page)

    # Filter out pull requests - any entry with a pull_request key is a PR
    return [issue for issue in issues_list if "pull_request" not in issue]


def ensure_label(owner, repo, name, colour, description):
    """Create a label if it does not exist. Idempotent.

    If the label already exists, it is left untouched rather than updated.
    Returns True if the label was created, False if it already existed.
    """
    # Try to get the label first
    try:
        gh.api(f"repos/{owner}/{repo}/labels/{urllib.parse.quote(name, safe='')}")
        # Label exists, do nothing
        return False
    except gh.GhError:
        # Label does not exist, create it
        payload = {"name": name, "color": colour, "description": description}
        gh.api(f"repos/{owner}/{repo}/labels", method="POST", body=payload)
        return True


# One query, paginated, for every open issue and everything review and
# roadmap need about it. The call count does not grow with the number of
# issues until a page fills, where the old path made two calls per issue.
GRAPH_PAGE = 50
_GRAPH = """
query DeskworkGraph($owner: String!, $name: String!, $after: String,
                    $comments: Boolean!, $board: Boolean!) {
  repository(owner: $owner, name: $name) {
    issues(first: %d, after: $after, states: [OPEN],
           orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title url
        issueType { name }
        labels(first: 100) { nodes { name } }
        parent { url }
        blockedBy(first: 100) { totalCount nodes { title state url } }
        comments(first: 100) @include(if: $comments) { totalCount nodes { body } }
        projectItems(first: 20) @include(if: $board) {
          nodes {
            project { id }
            fieldValueByName(name: "Status") {
              ... on ProjectV2ItemFieldSingleSelectValue { name }
            }
          }
        }
      }
    }
  }
}""" % GRAPH_PAGE


class IncompleteRead(Exception):
    """GitHub returned fewer items than it says exist. Refuse to act on it."""


@dataclass
class Issue:
    ref: ids.Ref
    title: str
    type: str = None
    labels: list = field(default_factory=list)
    parent: ids.Ref = None
    blockers: list = field(default_factory=list)  # deps.Blocker, open and closed
    board_status: str = None
    memory: "memory.Memory" = None

    @property
    def open_blockers(self):
        return [b.ref for b in self.blockers if b.state == "OPEN"]

    def in_triage(self, triage_label, triage_status=None):
        """Filed and not yet reviewed: the Triage label, or Triage on the board."""
        if triage_label and triage_label in self.labels:
            return True
        return bool(triage_status) and self.board_status == triage_status


def _issue(node, project, with_memory):
    ref = ids.from_url(node["url"])
    blocked = node.get("blockedBy") or {}
    nodes = blocked.get("nodes") or []
    if blocked.get("totalCount", len(nodes)) != len(nodes):
        raise IncompleteRead(f"{ref}: {blocked['totalCount']} blockers, {len(nodes)} returned")
    status = None
    for item in (node.get("projectItems") or {}).get("nodes") or []:
        if (item.get("project") or {}).get("id") == project:
            status = (item.get("fieldValueByName") or {}).get("name")
    mem = None
    if with_memory:
        comments = node.get("comments") or {}
        bodies = [c.get("body") or "" for c in comments.get("nodes") or []]
        marked = next((b for b in bodies if memory.MARKER in b), None)
        if marked is None and comments.get("totalCount", 0) > len(bodies):
            mem = memory.read(ref)  # the marker is past the first page
        else:
            mem = memory.parse(marked or "")
    return Issue(
        ref=ref,
        title=node.get("title", ""),
        type=(node.get("issueType") or {}).get("name"),
        labels=[label["name"] for label in (node.get("labels") or {}).get("nodes") or []],
        parent=ids.from_url(node["parent"]["url"]) if node.get("parent") else None,
        blockers=[
            deps.Blocker(ids.from_url(b["url"]), b.get("state", "OPEN"), b.get("title", ""))
            for b in nodes
        ],
        board_status=status,
        memory=mem,
    )


def read_graph(owner, name, project=None, with_memory=False):
    """Every open issue in owner/name, with its blockers and their state."""
    found, after = [], None
    while True:
        data = gh.graphql(
            _GRAPH, owner=owner, name=name, after=after,
            comments=bool(with_memory), board=bool(project),
        )
        page = data["repository"]["issues"]
        found.extend(_issue(node, project, with_memory) for node in page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            return found
        after = page["pageInfo"]["endCursor"]
