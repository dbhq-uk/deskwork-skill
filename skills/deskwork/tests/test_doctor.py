"""doctor, run against a fake GitHub that has drifted in one way at a time."""
import pytest

from conftest import deskwork


def _doctor(project):
    return deskwork("doctor", cwd=project)


def test_a_board_that_matches_its_config_is_clear(project, github):
    github.issue(1, board_status="Triage")
    result = _doctor(project)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "no drift" in result.stdout


@pytest.mark.parametrize("setup, expected", [
    (lambda g: g.set(labels=["triage", "area:infra"]), "label area:docs is in the config and not in the repository"),
    (lambda g: g.set(labels=["area:infra", "area:docs"]), "label triage is in the config and not in the repository"),
    (lambda g: g.set(labels=["triage", "area:infra", "area:docs", "area:old"]), "label area:old is in the repository and not in the config"),
    (lambda g: g.set(issue_types=["Bug", "Task"]), "issue type Feature is in the config and not enabled"),
    (lambda g: g.set(issue_types=[]), "this repository has no issue types"),
    (lambda g: g.issue(7), "1 open issues are not on the board: #7"),
])
def test_each_kind_of_drift_is_reported_and_fails(project, github, setup, expected):
    setup(github)
    result = _doctor(project)
    assert result.returncode == 1
    assert expected in result.stdout


def test_a_status_field_without_the_triage_option_is_drift(project, github):
    github.state["board"]["options"] = [o for o in github.state["board"]["options"] if o["name"] != "Triage"]
    github.save()
    result = _doctor(project)
    assert result.returncode == 1
    assert "no Triage option" in result.stdout


def test_a_missing_project_scope_fails(project, github):
    github.fault(no_project_scope=True)
    result = _doctor(project)
    assert result.returncode == 1
    assert "gh auth refresh -s project" in result.stdout


def test_a_gh_older_than_2_94_fails(project, github):
    github.set(version="2.93.0")
    result = _doctor(project)
    assert result.returncode == 1
    assert "gh 2.94.0 or later" in result.stderr


def test_without_a_board_it_checks_labels_and_types_only(project, github):
    config = project / ".github" / "deskwork.toml"
    config.write_text(config.read_text().replace('project = "PVT_kwDOABCD1234"\n', ""))
    github.fault(no_project_scope=True)  # would fail any board call
    result = _doctor(project)
    assert result.returncode == 0, result.stdout
    assert "no board configured" in result.stdout
