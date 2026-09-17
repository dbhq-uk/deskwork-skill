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


def test_capture_dry_run_does_not_write(tmp_path, monkeypatch):
    """--dry-run must not create an issue. Proven by failing all non-GET calls."""
    import sys
    sys.path.insert(0, str(SCRIPT.parents[0]))

    import gh
    import argparse
    import config as config_module
    import deskwork

    def reject_non_get(path, method="GET", body=None, extra_args=None):
        if method != "GET":
            raise AssertionError(f"capture --dry-run tried to write: {method} {path}")
        # Return search results for duplicate search
        if "search" in path:
            return {"items": []}
        return {}

    monkeypatch.setattr(gh, "api", reject_non_get)

    # Create a minimal valid config
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "deskwork.toml").write_text(
        'enabled = true\nproject = "PVT_x"\ndesigns = "docs/"\nroadmap = "roadmap.md"\n'
    )
    # Create git repo
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text(
        "[remote \"origin\"]\n    url = git@github.com:test/repo.git\n"
    )

    # Call the mode directly
    cfg = config_module.load(tmp_path)
    args = argparse.Namespace(
        title="Test", issue_type=None, area=None, dry_run=True, repo=tmp_path
    )
    result = deskwork.mode_capture(args, cfg)
    assert result == 0


def test_intake_dry_run_does_not_write(tmp_path, monkeypatch):
    """intake --dry-run must not call node_id or add_item."""
    import sys
    sys.path.insert(0, str(SCRIPT.parents[0]))

    import gh
    import argparse
    import config as config_module
    import deskwork
    import board

    def reject_non_get(path, method="GET", body=None, extra_args=None):
        if method != "GET":
            raise AssertionError(f"intake --dry-run tried to write: {method} {path}")
        # Return empty lists for list_open
        if "issues" in path and extra_args and "--paginate" in extra_args:
            return [[]]
        return {}

    def mock_items(project_id):
        return []

    monkeypatch.setattr(gh, "api", reject_non_get)
    monkeypatch.setattr(board, "items", mock_items)

    # Create a minimal valid config
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "deskwork.toml").write_text(
        'enabled = true\nproject = "PVT_x"\ndesigns = "docs/"\nroadmap = "roadmap.md"\n'
    )
    # Create git repo
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text(
        "[remote \"origin\"]\n    url = git@github.com:test/repo.git\n"
    )

    # Call the mode directly
    cfg = config_module.load(tmp_path)
    args = argparse.Namespace(dry_run=True, repo=tmp_path)
    result = deskwork.mode_intake(args, cfg)
    assert result == 0


def test_init_dry_run_does_not_write(tmp_path, monkeypatch):
    """init --dry-run must not call ensure_label or ensure_field."""
    import sys
    sys.path.insert(0, str(SCRIPT.parents[0]))

    import gh
    import argparse
    import config as config_module
    import deskwork

    def reject_non_get(path, method="GET", body=None, extra_args=None):
        if method != "GET":
            raise AssertionError(f"init --dry-run tried to write: {method} {path}")
        return {}

    monkeypatch.setattr(gh, "api", reject_non_get)

    # Create a minimal valid config
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "deskwork.toml").write_text(
        'enabled = true\nproject = "PVT_x"\ndesigns = "docs/"\nroadmap = "roadmap.md"\n'
        '[labels]\narea = ["infra", "web"]\n'
        '[fields]\nStatus = "Triage"\n'
    )
    # Create git repo
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text(
        "[remote \"origin\"]\n    url = git@github.com:test/repo.git\n"
    )

    # Call the mode directly
    cfg = config_module.load(tmp_path)
    args = argparse.Namespace(dry_run=True, repo=tmp_path)
    result = deskwork.mode_init(args, cfg)
    assert result == 0
