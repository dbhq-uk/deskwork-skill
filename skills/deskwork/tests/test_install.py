"""Both installers refuse a gh older than 2.94 and install nothing."""
import os
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]


def _run(script, tmp_path, gh_version):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    gh = bindir / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        f'if [ "$1" = "--version" ]; then echo "gh version {gh_version} (2026-01-01)"; fi\n'
        "exit 0\n"
    )
    gh.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "HOME": str(home), "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"}
    result = subprocess.run(["bash", str(ROOT / script)], env=env, capture_output=True, text=True)
    return result, home


@pytest.mark.parametrize("script, installed", [
    ("install.sh", ".claude/skills/deskwork"),
    ("install-codex.sh", ".codex/skills/deskwork"),
])
@pytest.mark.parametrize("old", ["2.93.1", "1.99.0"])
def test_an_old_gh_is_refused_and_nothing_is_installed(tmp_path, script, installed, old):
    result, home = _run(script, tmp_path, old)
    assert result.returncode == 1, result.stdout
    assert "needs gh 2.94 or later" in result.stdout
    assert not (home / installed).exists()


@pytest.mark.parametrize("script, installed", [
    ("install.sh", ".claude/skills/deskwork"),
    ("install-codex.sh", ".codex/skills/deskwork/SKILL.md"),
])
@pytest.mark.parametrize("new", ["2.94.0", "2.100.0", "3.0.0"])
def test_a_current_gh_installs(tmp_path, script, installed, new):
    result, home = _run(script, tmp_path, new)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (home / installed).exists()
