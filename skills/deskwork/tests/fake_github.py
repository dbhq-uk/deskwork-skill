#!/usr/bin/env python3
"""A stand-in for gh that keeps a small GitHub in a JSON file.

Installed on PATH as `gh` by the `github` fixture. It answers the commands
deskwork sends, changes its state on a write, and logs every call, so a test
can run a real deskwork mode end to end and then look at what GitHub would
hold afterwards. Anything it does not recognise fails loudly: a test must not
pass because an unexpected call was quietly answered.

State, keyed "owner/repo#N" so cross-repository edges work:

    {"repo": "owner/repo",
     "issues": {"owner/repo#1": {"title": "...", "state": "OPEN", "type": "Task",
                                 "labels": [], "blockedBy": ["owner/repo#2"],
                                 "parent": null, "comments": [{"id": 7, "body": "..."}],
                                 "board_status": null, "body": ""}},
     "project": null,
     "faults": {"link_instead": "owner/repo#99"},
     "calls": []}
"""
import json
import os
import re
import sys

STATE = os.environ["DESKWORK_FAKE_STATE"]


def load():
    with open(STATE) as handle:
        return json.load(handle)


def save(state):
    with open(STATE, "w") as handle:
        json.dump(state, handle, indent=1)


def fail(message, code=1):
    sys.stderr.write(f"fake github: {message}\n")
    sys.exit(code)


def url(key):
    owner_repo, number = key.split("#")
    return f"https://github.com/{owner_repo}/issues/{number}"


def key_from(value, repo):
    """An issue key from a number (in repo) or an issue URL."""
    match = re.match(r"^https://github\.com/([^/]+/[^/]+)/issues/(\d+)$", value)
    if match:
        return f"{match.group(1)}#{match.group(2)}"
    if value.isdigit():
        return f"{repo}#{value}"
    fail(f"cannot read an issue from {value!r}")


def flag(argv, name, default=None):
    if name in argv:
        index = argv.index(name)
        if index + 1 < len(argv):
            return argv[index + 1]
    return default


def issue_json(state, key, fields):
    issue = state["issues"].get(key)
    if issue is None:
        fail(f"GraphQL: Could not resolve to an issue with the number of {key.split('#')[1]}.")
    number = int(key.split("#")[1])
    blockers = [b for b in issue.get("blockedBy", [])]
    full = {
        "number": number,
        "id": issue.get("node_id", f"I_kw{key.replace('/', '_').replace('#', '_')}"),
        "title": issue["title"],
        "state": issue.get("state", "OPEN"),
        "url": url(key),
        "body": issue.get("body", ""),
        "labels": [{"name": name} for name in issue.get("labels", [])],
        "issueType": {"name": issue["type"]} if issue.get("type") else None,
        "parent": {"url": url(issue["parent"]), "number": int(issue["parent"].split("#")[1])}
        if issue.get("parent") else None,
        "blockedBy": {
            "totalCount": len(blockers),
            "nodes": [
                {"number": int(b.split("#")[1]), "url": url(b),
                 "state": state["issues"].get(b, {}).get("state", "OPEN"),
                 "title": state["issues"].get(b, {}).get("title", "")}
                for b in blockers
            ],
        },
    }
    return {name: full[name] for name in fields}


def cmd_issue(state, argv):
    verb = argv[1]
    repo = flag(argv, "-R", state["repo"])
    if verb == "view":
        key = key_from(argv[2], repo)
        fields = flag(argv, "--json", "").split(",")
        print(json.dumps(issue_json(state, key, fields)))
        return
    if verb == "edit":
        key = key_from(argv[2], repo)
        issue = state["issues"].get(key) or fail(f"no issue {key}")
        faults = state.get("faults", {})
        for index, arg in enumerate(argv):
            if arg == "--add-blocked-by":
                target = key_from(argv[index + 1], repo)
                if target not in state["issues"]:
                    fail(f"GraphQL: Could not resolve to an issue ({target})")
                if faults.get("ignore_edits"):
                    continue
                target = faults.get("link_instead", target)
                if target not in issue.setdefault("blockedBy", []):
                    issue["blockedBy"].append(target)
            elif arg == "--remove-blocked-by":
                target = key_from(argv[index + 1], repo)
                if faults.get("ignore_edits"):
                    continue
                if target in issue.get("blockedBy", []):
                    issue["blockedBy"].remove(target)
        print(url(key))
        return
    fail(f"unsupported: gh {' '.join(argv)}")


def graph_page(state, variables, query):
    size = int(re.search(r"issues\(first:\s*(\d+)", query).group(1))
    owner_repo = f"{variables['owner']}/{variables['name']}"
    keys = sorted(
        (k for k, v in state["issues"].items()
         if k.startswith(owner_repo + "#") and v.get("state", "OPEN") == "OPEN"),
        key=lambda k: int(k.split("#")[1]),
    )
    start = int(variables.get("after") or 0)
    page = keys[start:start + size]
    nodes = []
    for key in page:
        issue = state["issues"][key]
        node = issue_json(state, key, ["number", "title", "url", "issueType", "parent"])
        node["labels"] = {"nodes": [{"name": n} for n in issue.get("labels", [])]}
        full = issue_json(state, key, ["blockedBy"])["blockedBy"]
        node["blockedBy"] = {"totalCount": full["totalCount"], "nodes": full["nodes"][:100]}
        if variables.get("comments"):
            comments = issue.get("comments", [])
            node["comments"] = {
                "totalCount": len(comments),
                "nodes": [{"body": c["body"]} for c in comments[:100]],
            }
        if variables.get("board"):
            status = issue.get("board_status")
            node["projectItems"] = {"nodes": [] if status is None and not issue.get("on_board") else [
                {"project": {"id": state.get("project")},
                 "fieldValueByName": {"name": status} if status else None}
            ]}
        nodes.append(node)
    end = start + len(page)
    return {"repository": {"issues": {
        "pageInfo": {"hasNextPage": end < len(keys), "endCursor": str(end)},
        "nodes": nodes,
    }}}


def cmd_graphql(state, body):
    query = body["query"]
    variables = body.get("variables") or {}
    if "query DeskworkGraph" in query:
        if variables.get("board") and state.get("faults", {}).get("no_project_scope"):
            fail("Your token has not been granted the required scopes to execute this query. "
                 "The 'project' field requires one of the following scopes: ['read:project']")
        print(json.dumps({"data": graph_page(state, variables, query)}))
        return
    fail(f"unsupported GraphQL operation: {query.strip().splitlines()[0]}")


def cmd_api(state, argv, stdin):
    path = next(a for a in argv[1:] if not a.startswith("-") and a not in ("PATCH", "POST", "GET", "DELETE"))
    method = flag(argv, "-X", "GET")
    if path == "graphql":
        cmd_graphql(state, json.loads(stdin))
        return
    match = re.match(r"^repos/([^/]+/[^/]+)/issues/(\d+)/comments$", path)
    if match:
        key = f"{match.group(1)}#{match.group(2)}"
        issue = state["issues"].get(key) or fail(f"no issue {key}")
        comments = issue.setdefault("comments", [])
        if method == "POST":
            comment = {"id": state.get("next_comment_id", 9000), "body": json.loads(stdin)["body"]}
            state["next_comment_id"] = comment["id"] + 1
            comments.append(comment)
            print(json.dumps(comment))
            return
        if "--paginate" in argv:
            pages = [comments[i:i + 30] for i in range(0, len(comments), 30)] or [[]]
            print(json.dumps(pages if "--slurp" in argv else sum(pages, [])))
            return
        print(json.dumps(comments[:30]))
        return
    match = re.match(r"^repos/([^/]+/[^/]+)/issues/comments/(\d+)$", path)
    if match:
        for issue in state["issues"].values():
            for comment in issue.get("comments", []):
                if comment["id"] == int(match.group(2)):
                    if method == "PATCH":
                        if not state.get("faults", {}).get("drop_comment_edits"):
                            comment["body"] = json.loads(stdin)["body"]
                    print(json.dumps(comment))
                    return
        fail(f"no comment {match.group(2)}")
    fail(f"unsupported: gh {' '.join(argv)}")


def main():
    argv = sys.argv[1:]
    # Read stdin only when gh would: an inherited stdin may never close.
    stdin = sys.stdin.read() if flag(argv, "--input") == "-" else ""
    state = load()
    state.setdefault("calls", []).append({"argv": argv, "stdin": stdin})
    try:
        if argv == ["--version"]:
            print(f"gh version {state.get('version', '2.100.0')} (2026-09-03)")
        elif argv[:2] == ["repo", "view"]:
            print(json.dumps({"nameWithOwner": state["repo"]}))
        elif argv[:1] == ["issue"]:
            cmd_issue(state, argv)
        elif argv[:1] == ["api"]:
            cmd_api(state, argv, stdin)
        else:
            fail(f"unsupported: gh {' '.join(argv)}")
    finally:
        save(state)


if __name__ == "__main__":
    main()
