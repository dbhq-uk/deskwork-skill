"""Shared fixtures. Nothing here touches the network, a token or an agent."""
import json
import os
import pathlib
import stat
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))

GIT_ENV = {
    "GIT_AUTHOR_NAME": "deskwork tests",
    "GIT_AUTHOR_EMAIL": "tests@example.com",
    "GIT_COMMITTER_NAME": "deskwork tests",
    "GIT_COMMITTER_EMAIL": "tests@example.com",
    "GIT_CONFIG_NOSYSTEM": "1",
}


def git(cwd, *args):
    """Run git in a test repository, with an identity and no user config."""
    env = {**os.environ, **GIT_ENV, "HOME": str(cwd)}
    return subprocess.run(
        ["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture(autouse=True)
def git_identity(monkeypatch):
    """So a commit made by the code under test has an author, as in real use."""
    for key, value in GIT_ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def fake_gh(tmp_path, monkeypatch):
    """A gh that answers from a table of canned responses, keyed on argv."""
    def install(responses):
        canned = tmp_path / "responses.json"
        canned.write_text(json.dumps(responses))
        bindir = tmp_path / "bin"
        bindir.mkdir(exist_ok=True)
        shim = bindir / "gh"
        shim.write_text((HERE / "fake_gh.py").read_text())
        shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ["PATH"])
        monkeypatch.setenv("DESKWORK_FAKE_GH", str(canned))
    return install


SCRIPT = HERE.parent / "scripts" / "deskwork.py"
CONFIG = (
    'enabled = true\nproject = "PVT_kwDOABCD1234"\ndesigns = "docs/designs/"\n'
    'roadmap = "roadmap.md"\n'
)


class FakeGitHub:
    """A small GitHub behind a fake gh on PATH. See fake_github.py."""

    def __init__(self, tmp_path, monkeypatch):
        self.path = tmp_path / "github.json"
        self.state = {
            "repo": "owner/repo", "issues": {}, "project": "PVT_kwDOABCD1234",
            "faults": {}, "calls": [],
        }
        bindir = tmp_path / "github-bin"
        bindir.mkdir()
        shim = bindir / "gh"
        shim.write_text((HERE / "fake_github.py").read_text())
        shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ["PATH"])
        monkeypatch.setenv("DESKWORK_FAKE_STATE", str(self.path))
        self.save()

    @staticmethod
    def key(ref, repo="owner/repo"):
        return ref if isinstance(ref, str) else f"{repo}#{ref}"

    def issue(self, number, title="", *, repo="owner/repo", state="OPEN", labels=(),
              blocked_by=(), type="Task", comments=(), board_status=None, parent=None):
        self.state["issues"][self.key(number, repo)] = {
            "title": title or f"Issue {number}", "state": state, "type": type,
            "labels": list(labels), "blockedBy": [self.key(b) for b in blocked_by],
            "comments": [dict(c) for c in comments], "board_status": board_status,
            "parent": self.key(parent) if parent is not None else None, "body": "",
        }
        self.save()

    def fault(self, **faults):
        self.state["faults"].update(faults)
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.state, indent=1))

    def load(self):
        self.state = json.loads(self.path.read_text())
        return self.state

    @property
    def calls(self):
        return self.load()["calls"]

    def writes(self):
        """Every call that changes GitHub, as argv lists."""
        out = []
        for call in self.calls:
            argv = call["argv"]
            if argv[:2] in (["issue", "edit"], ["issue", "create"]) or (
                argv[:1] == ["api"] and ("-X" in argv) and argv[argv.index("-X") + 1] != "GET"
            ) or (argv[:2] == ["api", "graphql"]
                  and json.loads(call["stdin"])["query"].lstrip().startswith("mutation")):
                out.append(argv)
        return out

    def blockers(self, number):
        return self.load()["issues"][self.key(number)]["blockedBy"]

    def comments(self, number):
        return self.load()["issues"][self.key(number)]["comments"]


@pytest.fixture
def github(tmp_path, monkeypatch):
    return FakeGitHub(tmp_path, monkeypatch)


@pytest.fixture
def project(tmp_path):
    """An opted-in clone of owner/repo, with an upstream listed before origin."""
    top = tmp_path / "project"
    (top / ".github").mkdir(parents=True)
    (top / ".github" / "deskwork.toml").write_text(CONFIG)
    git(top, "init", "-q", "-b", "main")
    git(top, "add", ".")
    git(top, "commit", "-q", "-m", "opt in")
    git(top, "remote", "add", "upstream", "https://github.com/upstream-org/repo.git")
    git(top, "remote", "add", "origin", "git@github.com:owner/repo.git")
    return top


def deskwork(*args, cwd, stdin=None):
    """Run deskwork.py as the agent would, and return the finished process."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=cwd, input=stdin,
        capture_output=True, text=True,
    )
