"""Which repository deskwork is working in.

The root comes from git, so a worktree (where .git is a file) and a
subdirectory both find the same root and the same config. The name comes
from the origin remote, confirmed by gh, so a clone that also has an upstream
files into its own repository rather than into whichever remote is listed
first. gh returns the canonical name, so a renamed repository resolves to
its current name rather than through a redirect.
"""
import pathlib
import re

import gh
import git


class NotARepo(Exception):
    """The path is not inside a git work tree."""


_REMOTE = re.compile(
    r"^(?:[a-z][a-z0-9+.-]*://)?(?:[^@/]+@)?(?P<host>[^/:]+)(?::\d+)?[:/]"
    r"(?P<owner>[^/]+)/(?P<name>[^/]+?)(?:\.git)?/?$"
)


def root(path):
    """The top of the work tree that contains path."""
    try:
        out = git.run(["rev-parse", "--show-toplevel"], cwd=path)
    except (git.GitError, OSError) as error:
        raise NotARepo(f"{path} is not inside a git repository ({error})") from error
    return pathlib.Path(out.strip())


def parse_remote(url):
    """(host, owner, name) from an https, ssh:// or scp-style remote URL."""
    match = _REMOTE.match(url.strip())
    if not match:
        raise ValueError(f"cannot read owner/repo from the remote URL {url!r}")
    return match.group("host"), match.group("owner"), match.group("name")


def origin_url(top):
    """The origin remote's URL, or None when there is no remote called origin."""
    try:
        return git.run(["remote", "get-url", "origin"], cwd=top).strip() or None
    except git.GitError:
        return None


def name_with_owner(top):
    """(owner, name) of the repository deskwork files into.

    The origin remote when there is one. Without one, gh's own choice, which
    honours `gh repo set-default`.
    """
    url = origin_url(top)
    if url:
        host, owner, name = parse_remote(url)
        target = f"{owner}/{name}" if host == "github.com" else f"{host}/{owner}/{name}"
        data = gh.run_json(["repo", "view", target, "--json", "nameWithOwner"], cwd=top)
    else:
        data = gh.run_json(["repo", "view", "--json", "nameWithOwner"], cwd=top)
    owner, _, name = (data or {}).get("nameWithOwner", "").partition("/")
    if not owner or not name:
        raise ValueError(f"gh did not return a repository name for {top}")
    return owner, name
