"""Filing issues, finding duplicates, and reading the graph.

Filing goes through gh issue create, which since gh 2.94 sets the issue type,
the parent and blocked-by edges itself, so nothing here builds a REST payload
or resolves an id. Every issue filed is read back before it is reported.
"""
import datetime
import re
from dataclasses import dataclass, field

import deps
import gh
import ids
import memory

SECTIONS = {
    "Bug": ["Context", "Expected", "Actual", "Acceptance"],
    "Feature": ["Context", "Proposal", "Acceptance", "Out of scope"],
    "Task": ["Context", "Acceptance"],
}
NOT_STATED = "_not stated_"
TRIAGE_COLOUR = "FBCA04"
AREA_COLOUR = "C5DEF5"

# Words that carry no signal for spotting a duplicate, dropped regardless of
# length. Dropping by length is backwards: it throws away an acronym like CSP
# or an error code, the words a title is most likely to be distinctive by.
_STOP_WORDS = frozenset({
    "a", "an", "the",
    "and", "or", "but", "nor", "so", "if", "than", "then",
    "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did",
    "has", "have", "had",
    "in", "on", "at", "by", "to", "of", "for", "with", "from", "as", "when", "after",
    "it", "its", "this", "that", "these", "those",
    "not", "no",
    "will", "can", "should", "would", "could",
})
DUPLICATE_SCORE = 0.5  # title overlap at or above this is a candidate
RECENTLY_CLOSED_DAYS = 30


def sections_for(kind):
    return SECTIONS.get(kind, SECTIONS["Task"])


def body_for(kind, **supplied):
    """The body skeleton for an issue type, with any sections supplied filled in."""
    aliases = {"out_of_scope": "Out of scope"}
    given = {aliases.get(k, k.capitalize()): v for k, v in supplied.items()}
    lines = []
    for heading in sections_for(kind):
        lines += [f"**{heading}**", "", given.get(heading, NOT_STATED), ""]
    return "\n".join(lines).strip()


def body_problems(kind, body):
    """Why a body cannot be filed as this type, or [] if it can."""
    problems = []
    if not body.strip():
        return ["the body is empty"]
    if NOT_STATED in body:
        problems.append(f"the body still says {NOT_STATED}. Fill every section or cut it.")
    for heading in sections_for(kind):
        pattern = rf"^\s*(?:\*\*{re.escape(heading)}\*\*|#{{2,3}}\s+{re.escape(heading)})\s*:?\s*$"
        if not re.search(pattern, body, re.MULTILINE | re.IGNORECASE):
            problems.append(f"a {kind} needs a {heading} section (a line reading **{heading}**)")
    return problems


def _stem(word):
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)]
            if len(word) > 3 and word[-1] == word[-2] and word[-1] not in "aeiou":
                word = word[:-1]  # dropped -> drop
            return word
    return word


def tokens(title):
    words = re.findall(r"[a-z0-9][a-z0-9+#.-]*", title.lower())
    return {_stem(w) for w in words if w not in _STOP_WORDS}


def similarity(a, b):
    left, right = tokens(a), tokens(b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def duplicate_candidates(owner, name, title, now=None):
    """Issues that might already be this one: (candidates, warning).

    Two sources, because each misses what the other catches. Title overlap
    against every open issue has no index lag, so it sees an issue a parallel
    agent filed a moment ago. GitHub's hybrid search matches on meaning, so it
    sees a reworded title, and it includes issues closed in the last 30 days.
    A search failure is a warning, not a stop.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    found = {}
    listed = gh.run_json(
        ["issue", "list", "-R", f"{owner}/{name}", "--state", "open",
         "--json", "number,title,url", "--limit", "5000"]
    ) or []
    for issue in listed:
        score = similarity(title, issue["title"])
        if score >= DUPLICATE_SCORE:
            found[issue["number"]] = {
                "ref": f"#{issue['number']}", "title": issue["title"], "state": "OPEN",
                "score": round(score, 2), "found_by": "title overlap",
            }
    warning = None
    try:
        hits = gh.api("search/issues", extra_args=[
            "-X", "GET", "-f", f"q=repo:{owner}/{name} is:issue {title}",
            "-f", "search_type=hybrid", "-f", "per_page=10",
        ]) or {}
    except gh.GhError as error:
        hits, warning = {}, f"hybrid search failed, so only title overlap was checked: {error}"
    cutoff = now - datetime.timedelta(days=RECENTLY_CLOSED_DAYS)
    for item in (hits.get("items") or [])[:5]:
        if "pull_request" in item or item["number"] in found:
            continue
        state = item.get("state", "open").upper()
        if state == "CLOSED":
            closed = datetime.datetime.fromisoformat(item["closed_at"].replace("Z", "+00:00"))
            if closed < cutoff:
                continue
        found[item["number"]] = {
            "ref": f"#{item['number']}", "title": item["title"], "state": state,
            "score": round(similarity(title, item["title"]), 2), "found_by": "hybrid search",
        }
    ordered = sorted(found.values(), key=lambda c: (-c["score"], int(c["ref"][1:])))
    return ordered, warning


def create(owner, name, title, body, issue_type, labels, parent=None, blocked_by=()):
    """File the issue with gh issue create, and return its Ref."""
    home = (owner, name)
    args = ["issue", "create", "-R", f"{owner}/{name}", "--title", title, "--body-file", "-"]
    for label in labels:
        args += ["--label", label]
    if issue_type:
        args += ["--type", issue_type]
    if parent is not None:
        args += ["--parent", parent.gh_arg(home)]
    if blocked_by:
        args += ["--blocked-by", ",".join(b.gh_arg(home) for b in blocked_by)]
    out = gh.run(args, stdin_data=body, write=True)
    url = out.strip().splitlines()[-1] if out.strip() else ""
    return ids.from_url(url)


def check_filed(ref, title, body, issue_type, labels, parent, blocked_by):
    """Read the new issue back. Returns (node id, [what is not as asked])."""
    data = gh.run_json([
        "issue", "view", str(int(ref.number)), "-R", ref.repo_arg,
        "--json", "id,number,title,body,labels,issueType,parent,blockedBy",
    ])
    if data["number"] != int(ref.number):
        raise ids.MismatchedIssue(f"asked for {ref}, GitHub returned number {data['number']}")
    problems = []
    if data["title"] != title:
        problems.append(f"the title reads {data['title']!r}")
    if (data.get("body") or "").strip() != body.strip():
        problems.append("the body is not the body that was sent")
    have = {label["name"] for label in data.get("labels") or []}
    missing = [label for label in labels if label not in have]
    if missing:
        problems.append(f"labels missing: {', '.join(missing)}")
    got_type = (data.get("issueType") or {}).get("name")
    if issue_type and got_type != issue_type:
        problems.append(f"the type is {got_type!r}, not {issue_type!r}")
    got_parent = ids.from_url(data["parent"]["url"]) if data.get("parent") else None
    if parent is not None and got_parent != parent:
        problems.append(f"the parent is {got_parent}, not {parent}")
    got_blockers = {ids.from_url(n["url"]) for n in (data.get("blockedBy") or {}).get("nodes") or []}
    for blocker in blocked_by:
        if blocker not in got_blockers:
            problems.append(f"it is not blocked by {blocker}")
    return ids.NodeId(data["id"]), problems


def repo_labels(owner, name):
    return {
        label["name"] for label in
        gh.run_json(["label", "list", "-R", f"{owner}/{name}", "--json", "name", "--limit", "1000"]) or []
    }


def create_label(owner, name, label, colour, description):
    gh.run(
        ["label", "create", label, "-R", f"{owner}/{name}", "--color", colour,
         "--description", description],
        write=True,
    )


_TYPES = """
query DeskworkIssueTypes($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) { issueTypes(first: 50) { nodes { name isEnabled } } }
}"""


def repo_issue_types(owner, name):
    """The issue types enabled for the repository. Empty for a personal one."""
    data = gh.graphql(_TYPES, owner=owner, name=name)
    types = ((data.get("repository") or {}).get("issueTypes") or {}).get("nodes") or []
    return [t["name"] for t in types if t.get("isEnabled", True)]


def open_issues(owner, name):
    """[(Ref, NodeId)] for every open issue, from one gh issue list."""
    listed = gh.run_json(
        ["issue", "list", "-R", f"{owner}/{name}", "--state", "open",
         "--json", "number,id", "--limit", "5000"]
    ) or []
    return [(ids.Ref(owner, name, ids.IssueNumber(i["number"])), ids.NodeId(i["id"])) for i in listed]


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
