"""init, run as the agent runs it, against a fake GitHub."""
import json

import config
from conftest import deskwork, git


def _no_triage_option(github):
    github.state["board"]["options"] = [o for o in github.state["board"]["options"] if o["name"] != "Triage"]
    github.save()


def test_in_a_repository_with_no_config_it_writes_a_starter_switched_off(tmp_path, github):
    top = tmp_path / "fresh"
    top.mkdir()
    git(top, "init", "-q")
    result = deskwork("init", cwd=top)
    assert result.returncode == 0, result.stderr
    written = top / ".github" / "deskwork.toml"
    assert written.exists() and "enabled = false" in written.read_text()
    assert config.load(top) is None
    assert github.calls == []  # nothing reached GitHub
    # And the gate still holds for everything else until someone switches it on.
    assert deskwork("doctor", cwd=top).returncode == 2
    again = deskwork("init", cwd=top)
    assert again.returncode == 2 and "enabled = true" in again.stderr


def test_it_creates_exactly_the_labels_capture_applies(project, github):
    github.set(labels=[])
    result = deskwork("init", cwd=project)
    assert result.returncode == 0, result.stderr
    assert github.load()["labels"] == ["triage", "area:infra", "area:docs"]
    # The fake refuses a label that does not exist, so capture proves the names match.
    body = "**Context**\n\nFound in the build.\n\n**Acceptance**\n\nIt builds."
    filed = deskwork("capture", "--title", "Fix the build", "--area", "docs", "--body-file", "-",
                     cwd=project, stdin=body)
    assert filed.returncode == 0, filed.stderr


def test_it_adds_the_triage_option_to_status_as_json_and_keeps_the_others(project, github):
    _no_triage_option(github)
    github.issue(1, board_status="Todo")
    result = deskwork("init", cwd=project)
    assert result.returncode == 0, result.stderr
    assert "created the Triage option on Status" in result.stdout
    state = github.load()
    assert [o["name"] for o in state["board"]["options"]] == ["Todo", "Done", "Triage"]
    assert state["issues"]["owner/repo#1"]["board_status"] == "Todo"
    (mutation,) = [json.loads(c["stdin"]) for c in state["calls"] if "mutation DeskworkAddOption" in c["stdin"]]
    for option in mutation["variables"]["options"]:
        assert isinstance(option, dict) and {"name", "color", "description"} <= set(option)


def test_a_second_run_reports_that_nothing_was_created(project, github):
    github.set(labels=[])
    _no_triage_option(github)
    assert deskwork("init", cwd=project).returncode == 0
    github.state = github.load()
    github.state["calls"] = []
    github.save()
    again = deskwork("init", cwd=project)
    assert again.returncode == 0
    assert "nothing to create" in again.stdout
    assert "created" not in again.stdout.replace("nothing to create", "")
    assert github.writes() == []


def test_dry_run_writes_nothing(project, github):
    github.set(labels=[])
    _no_triage_option(github)
    result = deskwork("init", "--dry-run", cwd=project)
    assert result.returncode == 0
    assert "would create label triage" in result.stdout
    assert "would add the Triage option" in result.stdout
    assert github.writes() == []


def test_labels_that_do_not_appear_after_creating_are_reported(project, github):
    github.set(labels=[])
    github.fault(drop_label_creates=True)
    result = deskwork("init", cwd=project)
    assert result.returncode == 4
    assert "not there after creating them" in result.stderr
