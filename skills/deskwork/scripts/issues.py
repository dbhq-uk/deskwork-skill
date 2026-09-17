"""Creating and finding issues.

gh issue create has no --type flag, so creation goes through the REST endpoint.
Issue types are the canonical GitHub categorisation; labels are the fallback
for an organisation that has not configured them.
"""
import urllib.parse

import gh
import ids

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
