import pytest

import repo
from conftest import git

VIEW_ORIGIN = "repo view owner/repo --json nameWithOwner"
ANSWER = {"stdout": '{"nameWithOwner": "owner/repo"}'}


@pytest.fixture
def clone(tmp_path):
    """A repository with one commit, origin at owner/repo."""
    top = tmp_path / "clone"
    top.mkdir()
    git(top, "init", "-q", "-b", "main")
    (top / "README.md").write_text("x\n")
    git(top, "add", "README.md")
    git(top, "commit", "-q", "-m", "first")
    git(top, "remote", "add", "origin", "git@github.com:owner/repo.git")
    return top


def test_the_root_is_found_from_a_subdirectory(clone):
    deep = clone / "src" / "lib"
    deep.mkdir(parents=True)
    assert repo.root(deep) == clone.resolve()


def test_the_root_is_found_in_a_worktree_where_dot_git_is_a_file(clone, tmp_path, fake_gh):
    worktree = tmp_path / "wt"
    git(clone, "worktree", "add", "-q", str(worktree), "-b", "side")
    assert (worktree / ".git").is_file()
    assert repo.root(worktree) == worktree.resolve()
    fake_gh({VIEW_ORIGIN: ANSWER})
    assert repo.name_with_owner(repo.root(worktree)) == ("owner", "repo")


def test_origin_wins_over_an_upstream_listed_first(tmp_path, fake_gh):
    top = tmp_path / "fork"
    top.mkdir()
    git(top, "init", "-q")
    git(top, "remote", "add", "upstream", "https://github.com/upstream-org/repo.git")
    git(top, "remote", "add", "origin", "https://github.com/owner/repo.git")
    # Only the origin lookup has an answer. Asking gh about upstream-org
    # would fail the test rather than quietly filing into someone else's repo.
    fake_gh({VIEW_ORIGIN: ANSWER})
    assert repo.name_with_owner(top) == ("owner", "repo")


def test_gh_supplies_the_canonical_name_after_a_rename(clone, fake_gh):
    git(clone, "remote", "set-url", "origin", "https://github.com/owner/old-name.git")
    fake_gh({"repo view owner/old-name --json nameWithOwner": ANSWER})
    assert repo.name_with_owner(clone) == ("owner", "repo")


def test_without_an_origin_gh_decides(tmp_path, fake_gh):
    top = tmp_path / "plain"
    top.mkdir()
    git(top, "init", "-q")
    git(top, "remote", "add", "mine", "https://github.com/owner/repo.git")
    fake_gh({"repo view --json nameWithOwner": ANSWER})
    assert repo.name_with_owner(top) == ("owner", "repo")


def test_a_directory_outside_any_repository_is_refused(tmp_path):
    outside = tmp_path / "nowhere"
    outside.mkdir()
    with pytest.raises(repo.NotARepo):
        repo.root(outside)


@pytest.mark.parametrize("url, expected", [
    ("git@github.com:owner/repo.git", ("github.com", "owner", "repo")),
    ("https://github.com/owner/repo.git", ("github.com", "owner", "repo")),
    ("https://github.com/owner/repo", ("github.com", "owner", "repo")),
    ("https://token@github.com/owner/repo.git", ("github.com", "owner", "repo")),
    ("ssh://git@github.com:22/owner/repo.git", ("github.com", "owner", "repo")),
    ("git@example.com:owner/my.repo.git", ("example.com", "owner", "my.repo")),
])
def test_remote_urls_are_parsed(url, expected):
    assert repo.parse_remote(url) == expected


def test_an_unreadable_remote_url_is_an_error_not_a_guess():
    with pytest.raises(ValueError):
        repo.parse_remote("/srv/git/local-only")
