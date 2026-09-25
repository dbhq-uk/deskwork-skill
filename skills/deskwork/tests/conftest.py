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
