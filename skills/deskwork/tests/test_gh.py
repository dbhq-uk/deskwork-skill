import json
import os
import pathlib
import stat
import sys

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import gh  # noqa: E402


@pytest.fixture
def fake_gh(tmp_path, monkeypatch):
    def install(responses):
        canned = tmp_path / "responses.json"
        canned.write_text(json.dumps(responses))
        bindir = tmp_path / "bin"
        bindir.mkdir(exist_ok=True)
        shim = bindir / "gh"
        source = pathlib.Path(__file__).parent / "fake_gh.py"
        shim.write_text(source.read_text())
        shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ["PATH"])
        monkeypatch.setenv("DESKWORK_FAKE_GH", str(canned))
    return install


def test_api_parses_json(fake_gh):
    fake_gh({"api repos/owner/repo/issues/1": {"stdout": '{"id": 42, "number": 1}'}})
    assert gh.api("repos/owner/repo/issues/1")["id"] == 42


def test_api_raises_on_failure(fake_gh):
    fake_gh({"api repos/owner/repo/issues/9": {"stdout": "", "exit": 1}})
    with pytest.raises(gh.GhError):
        gh.api("repos/owner/repo/issues/9")


def test_graphql_renders_bool_and_none_variables(fake_gh, monkeypatch):
    monkeypatch.setattr(gh, "_last_write", 0.0)
    fake_gh({
        "api graphql -f query=mutation -F flag=true -F note=null": {
            "stdout": '{"data": {"ok": true}}'
        }
    })
    assert gh.graphql("mutation", flag=True, note=None) == {"ok": True}


def test_graphql_paces_writes(fake_gh, monkeypatch):
    paced = []
    monkeypatch.setattr(gh, "_pace", lambda: paced.append(True))
    fake_gh({"api graphql -f query=mutation": {"stdout": '{"data": {"ok": true}}'}})
    gh.graphql("mutation")
    assert paced == [True]
