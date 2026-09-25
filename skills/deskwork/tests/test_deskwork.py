import json
import pathlib
import subprocess
import sys

import pytest

import deskwork
from conftest import git

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "deskwork.py"


def run(args, cwd):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args, "--repo", str(cwd)],
        capture_output=True, text=True,
    )


def test_without_a_config_it_refuses_and_says_why(tmp_path):
    git(tmp_path, "init", "-q")
    result = run(["capture", "--title", "x"], tmp_path)
    assert result.returncode == 2
    assert "deskwork.toml" in result.stderr
    assert "enabled" in result.stderr


def test_an_unknown_mode_is_rejected(tmp_path):
    assert run(["frobnicate"], tmp_path).returncode != 0


def test_no_module_can_close_or_delete_an_issue():
    """Constraint 1, second line. gh.py refuses these calls at run time
    (test_gh.py); this catches the plainest spellings before they run at all.

    A substring search for "close" is useless here: the docstrings say the
    word precisely because the code must not do the thing. So look for the
    calls that would actually close or delete an issue.
    """
    banned = (
        '"state": "closed"',
        "'state': 'closed'",
        "issue close",
        "issue delete",
        'method="DELETE"',
        "closeIssue(",
        "deleteIssue(",
    )
    scripts = SCRIPT.parent
    for path in sorted(scripts.glob("*.py")):
        source = path.read_text()
        for pattern in banned:
            assert pattern not in source, f"{path.name} can close or delete: {pattern}"


# The dry runs of capture, init and intake, and every write they make, are
# tested end to end against the fake GitHub in test_capture.py, test_init.py
# and test_intake.py.


def test_outside_a_git_repository_it_says_so(tmp_path):
    result = run(["doctor"], tmp_path)
    assert result.returncode == 1
    assert "not inside a git repository" in result.stderr


# Where deskwork is run from must not change which repository it works on.
# main() resolves the root and the name once, for every mode, so each case
# below checks every mode.

CONFIG = 'enabled = true\nproject = "PVT_x"\ndesigns = "docs/"\nroadmap = "roadmap.md"\n'
REPO_VIEW = {
    "--version": {"stdout": "gh version 2.100.0 (2026-09-03)\n"},
    "repo view owner/repo --json nameWithOwner": {"stdout": '{"nameWithOwner": "owner/repo"}'},
}


@pytest.fixture
def opted_in(tmp_path):
    top = tmp_path / "clone"
    (top / ".github").mkdir(parents=True)
    (top / ".github" / "deskwork.toml").write_text(CONFIG)
    git(top, "init", "-q", "-b", "main")
    git(top, "add", ".")
    git(top, "commit", "-q", "-m", "opt in")
    git(top, "remote", "add", "upstream", "https://github.com/upstream-org/repo.git")
    git(top, "remote", "add", "origin", "git@github.com:owner/repo.git")
    return top


def _dispatch(monkeypatch, start):
    seen = {}
    for mode in deskwork.MODES:
        def record(args, cfg, mode=mode):
            seen[mode] = (args.root, args.owner, args.name, cfg.roadmap)
            return 0
        monkeypatch.setattr(deskwork, f"mode_{mode}", record)
    for mode in deskwork.MODES:
        assert deskwork.main([mode, "--repo", str(start)]) == 0, mode
    return seen


def _where(opted_in, tmp_path, place):
    if place == "worktree":
        worktree = tmp_path / "wt"
        git(opted_in, "worktree", "add", "-q", str(worktree), "-b", "side")
        return worktree, worktree
    if place == "subdirectory":
        deep = opted_in / "src" / "lib"
        deep.mkdir(parents=True)
        return deep, opted_in
    return opted_in, opted_in


@pytest.mark.parametrize("place", ["worktree", "subdirectory", "root"])
def test_every_mode_finds_the_root_and_the_origin_repository(
        opted_in, tmp_path, fake_gh, monkeypatch, place):
    start, top = _where(opted_in, tmp_path, place)
    # upstream is listed before origin, and only origin has an answer.
    fake_gh(REPO_VIEW)
    seen = _dispatch(monkeypatch, start)
    assert set(seen) == set(deskwork.MODES)
    for mode, (root, owner, name, roadmap_path) in seen.items():
        assert root == top.resolve(), mode
        assert (owner, name) == ("owner", "repo"), mode
        assert roadmap_path == "roadmap.md", mode


def test_a_gh_older_than_2_94_stops_every_mode(opted_in, fake_gh, capsys):
    fake_gh({"--version": {"stdout": "gh version 2.90.0 (2026-04-01)\n"}})
    for mode in deskwork.MODES:
        assert deskwork.main([mode, "--repo", str(opted_in)]) == 1, mode
    assert "gh 2.94.0 or later" in capsys.readouterr().err


def test_a_real_mode_runs_from_a_subdirectory_of_a_worktree(opted_in, tmp_path, fake_gh):
    worktree = tmp_path / "wt"
    git(opted_in, "worktree", "add", "-q", str(worktree), "-b", "side")
    deep = worktree / "src"
    deep.mkdir()
    fake_gh({
        **REPO_VIEW,
        "api graphql --input -": {"stdout": json.dumps({"data": {"repository": {"issues": {
            "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []}}}})},
    })
    result = run(["roadmap", "--dry-run"], deep)
    assert result.returncode == 0, result.stderr
    assert "# Roadmap" in result.stdout
