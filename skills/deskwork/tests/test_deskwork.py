import pathlib
import subprocess
import sys

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "deskwork.py"


def run(args, cwd):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args, "--repo", str(cwd)],
        capture_output=True, text=True,
    )


def test_without_a_config_it_refuses_and_says_why(tmp_path):
    result = run(["capture", "--title", "x"], tmp_path)
    assert result.returncode == 2
    assert "deskwork.toml" in result.stderr
    assert "enabled" in result.stderr


def test_an_unknown_mode_is_rejected(tmp_path):
    assert run(["frobnicate"], tmp_path).returncode != 0


def test_no_module_can_close_or_delete_an_issue():
    """Constraint 1, tested rather than promised.

    A substring search for "close" is useless here: the docstrings say the
    word precisely because the code must not do the thing. So look for the
    calls that would actually close or delete an issue.
    """
    banned = (
        '"state": "closed"',
        "'state': 'closed'",
        "issue close",
        "issue delete",
        'method="DELETE"',  # permitted only in deps.py, checked below
    )
    scripts = SCRIPT.parent
    for path in sorted(scripts.glob("*.py")):
        source = path.read_text()
        for pattern in banned:
            if pattern == 'method="DELETE"' and path.name == "deps.py":
                continue  # removing a dependency link is allowed and gated
            assert pattern not in source, f"{path.name} can close or delete: {pattern}"
