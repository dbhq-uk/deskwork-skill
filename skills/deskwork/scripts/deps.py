"""Issue dependencies: blocked_by and blocking.

Every write resolves the issue number to a database id first, and reads the
edge back afterwards. The API accepts an issue number where an id belongs and
returns 201, having linked something else entirely.
"""
import gh
import ids


class WriteNotConfirmed(Exception):
    """The write returned success and the edge is not there."""


def _ref_from_issue(issue):
    url = issue["repository_url"]
    prefix, owner, repo = url.rsplit("/", 2)
    if not prefix.endswith("/repos"):
        raise ValueError(f"unexpected repository_url shape, expected .../repos/owner/repo: {url!r}")
    return ids.Ref(owner, repo, ids.IssueNumber(issue["number"]))


def _list(ref, direction):
    path = f"repos/{ref.owner}/{ref.repo}/issues/{int(ref.number)}/dependencies/{direction}"
    return [_ref_from_issue(issue) for issue in gh.api(path) or []]


def blocked_by(ref):
    return _list(ref, "blocked_by")


def blocking(ref):
    return _list(ref, "blocking")


def add_blocked_by(ref, blocker):
    blocker_id = ids.resolve(blocker)
    path = f"repos/{ref.owner}/{ref.repo}/issues/{int(ref.number)}/dependencies/blocked_by"
    gh.api(path, method="POST", body={"issue_id": ids.require_id(blocker_id)})
    if blocker not in blocked_by(ref):
        raise WriteNotConfirmed(f"{ref} should now be blocked by {blocker} and is not")


def remove_blocked_by(ref, blocker):
    blocker_id = ids.resolve(blocker)
    path = (
        f"repos/{ref.owner}/{ref.repo}/issues/{int(ref.number)}"
        f"/dependencies/blocked_by/{ids.require_id(blocker_id)}"
    )
    gh.api(path, method="DELETE")
    if blocker in blocked_by(ref):
        raise WriteNotConfirmed(f"{ref} should no longer be blocked by {blocker} and still is")
