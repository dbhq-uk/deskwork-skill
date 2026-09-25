"""capture, run as the agent runs it, against a fake GitHub."""
import json

import pytest

import issues
from conftest import deskwork

BUG = issues.body_for(
    "Bug",
    context="Seen while changing the upload path in `src/upload.py`.",
    expected="The last attempt is retried.",
    actual="The last attempt is dropped.",
    acceptance="A test covers the final attempt.",
)
TASK = issues.body_for("Task", context="Found in the build log.", acceptance="The warning is gone.")


def _created(github):
    return [c for c in github.calls if c["argv"][:2] == ["issue", "create"]]


def test_a_bug_is_filed_with_the_body_as_supplied(project, github):
    result = deskwork("capture", "--title", "Retry logic drops the last attempt", "--type", "Bug",
                      "--area", "infra", "--body-file", "-", cwd=project, stdin=BUG)
    assert result.returncode == 0, result.stderr
    assert "capture: filed #1" in result.stdout
    issue = github.load()["issues"]["owner/repo#1"]
    assert issue["body"] == BUG
    for heading in ("Context", "Expected", "Actual", "Acceptance"):
        assert f"**{heading}**" in issue["body"]
    assert issue["type"] == "Bug"
    assert issue["labels"] == ["triage", "area:infra"]


def test_with_no_type_it_sends_task(project, github):
    result = deskwork("capture", "--title", "Silence the build warning", "--body-file", "-",
                      cwd=project, stdin=TASK)
    assert result.returncode == 0, result.stderr
    (call,) = _created(github)
    assert call["argv"][call["argv"].index("--type") + 1] == "Task"


def test_a_body_still_saying_not_stated_is_refused_before_any_write(project, github):
    result = deskwork("capture", "--title", "Half written", "--type", "Bug", "--body-file", "-",
                      cwd=project, stdin=issues.body_for("Bug", context="Only this."))
    assert result.returncode == 1
    assert "_not stated_" in result.stderr
    assert github.writes() == []
    assert not [c for c in github.calls if c["argv"][:2] in (["issue", "list"], ["api", "search/issues"])]


def test_a_body_missing_a_section_for_its_type_is_refused(project, github):
    result = deskwork("capture", "--title", "Bug without actual", "--type", "Bug", "--body-file", "-",
                      cwd=project, stdin=TASK)
    assert result.returncode == 1
    assert "Expected" in result.stderr and "Actual" in result.stderr
    assert github.writes() == []


def test_the_template_prints_the_sections_for_the_type(project, github):
    result = deskwork("capture", "--template", "--type", "Feature", cwd=project)
    assert result.returncode == 0
    assert result.stdout.strip() == issues.body_for("Feature")


def test_a_type_the_config_does_not_list_is_refused(project, github):
    result = deskwork("capture", "--title", "Big thing", "--type", "Epic", "--body-file", "-",
                      cwd=project, stdin=TASK)
    assert result.returncode == 1 and "--type Epic" in result.stderr
    assert github.writes() == []


def test_an_area_the_config_does_not_list_is_refused(project, github):
    result = deskwork("capture", "--title", "Styling", "--area", "website", "--body-file", "-",
                      cwd=project, stdin=TASK)
    assert result.returncode == 1 and "--area website" in result.stderr
    assert github.writes() == []


def test_status_is_set_on_the_project_item_id_and_read_back(project, github):
    # The fake refuses any item id that does not start PVTI_, as GitHub does.
    result = deskwork("capture", "--title", "Silence the build warning", "--body-file", "-",
                      cwd=project, stdin=TASK)
    assert result.returncode == 0, result.stderr
    (status_call,) = [json.loads(c["stdin"]) for c in github.calls
                      if c["argv"][:2] == ["api", "graphql"] and "mutation DeskworkSetStatus" in c["stdin"]]
    assert status_call["variables"]["item"].startswith("PVTI_")
    assert github.load()["issues"]["owner/repo#1"]["board_status"] == "Triage"
    assert "Status Triage, read back" in result.stdout


def test_a_board_without_a_triage_option_fails_loudly_and_names_the_issue_already_filed(project, github):
    github.state["board"]["options"] = [o for o in github.state["board"]["options"] if o["name"] != "Triage"]
    github.save()
    result = deskwork("capture", "--title", "Silence the build warning", "--body-file", "-",
                      cwd=project, stdin=TASK)
    assert result.returncode == 4
    assert "capture: filed #1" in result.stdout
    assert "'Triage'" in result.stderr and "Board" in result.stderr
    assert "Do not file it again" in result.stderr


def test_without_a_board_nothing_touches_projects(project, github):
    config = project / ".github" / "deskwork.toml"
    config.write_text(config.read_text().replace('project = "PVT_kwDOABCD1234"\n', ""))
    result = deskwork("capture", "--title", "Silence the build warning", "--body-file", "-",
                      cwd=project, stdin=TASK)
    assert result.returncode == 0, result.stderr
    assert not [c for c in github.calls if "Deskwork" in c["stdin"] and "DeskworkGraph" not in c["stdin"]]
    assert github.load()["issues"]["owner/repo#1"]["labels"] == ["triage"]


def test_an_issue_that_does_not_read_back_as_asked_is_reported_not_refiled(project, github):
    github.fault(drop_labels_on_create=True)
    result = deskwork("capture", "--title", "Silence the build warning", "--body-file", "-",
                      cwd=project, stdin=TASK)
    assert result.returncode == 4
    assert "labels missing: triage" in result.stderr
    assert len(_created(github)) == 1


def test_parent_and_blockers_are_filed_and_read_back(project, github):
    github.issue(3, "Epic-sized parent")
    github.issue(9, "Upstream", repo="other/lib")
    result = deskwork("capture", "--title", "Split out the parser", "--parent", "3",
                      "--blocked-by", "other/lib#9", "--body-file", "-", cwd=project, stdin=TASK)
    assert result.returncode == 0, result.stderr
    issue = github.load()["issues"]["owner/repo#4"]
    assert issue["parent"] == "owner/repo#3" and issue["blockedBy"] == ["other/lib#9"]


# Duplicates are checked before filing, not after.

def test_a_reworded_open_duplicate_stops_the_filing(project, github):
    github.issue(12, "Retry logic drops the last attempt")
    result = deskwork("capture", "--title", "Last attempt is dropped by the retry logic",
                      "--type", "Bug", "--body-file", "-", cwd=project, stdin=BUG)
    assert result.returncode == 10
    report = json.loads(result.stdout)
    assert report["filed"] is False
    assert [c["ref"] for c in report["candidates"]] == ["#12"]
    assert _created(github) == []


def test_a_duplicate_closed_in_the_last_thirty_days_stops_the_filing(project, github):
    import datetime
    recent = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=5)).isoformat()
    github.issue(20, "Uploads time out on slow links", state="CLOSED", closed_at=recent)
    github.set(search_hits=["owner/repo#20"])
    result = deskwork("capture", "--title", "Large files fail over a poor connection",
                      "--body-file", "-", cwd=project, stdin=TASK)
    assert result.returncode == 10
    assert json.loads(result.stdout)["candidates"][0] == {
        "ref": "#20", "title": "Uploads time out on slow links", "state": "CLOSED",
        "score": 0.0, "found_by": "hybrid search",
    }
    assert _created(github) == []


def test_a_title_with_no_candidates_is_filed(project, github):
    github.issue(12, "Retry logic drops the last attempt")
    result = deskwork("capture", "--title", "Add a dark theme to settings", "--body-file", "-",
                      cwd=project, stdin=TASK)
    assert result.returncode == 0, result.stderr
    assert len(_created(github)) == 1


def test_file_files_even_when_candidates_exist(project, github):
    github.issue(12, "Retry logic drops the last attempt")
    result = deskwork("capture", "--title", "Retry logic drops the last attempt", "--file",
                      "--body-file", "-", cwd=project, stdin=TASK)
    assert result.returncode == 0, result.stderr
    assert len(_created(github)) == 1
    assert not [c for c in github.calls if c["argv"][:2] == ["api", "search/issues"]]


@pytest.mark.parametrize("extra", [[], ["--file"]])
def test_dry_run_writes_nothing(project, github, extra):
    result = deskwork("capture", "--title", "Silence the build warning", "--dry-run", *extra,
                      "--body-file", "-", cwd=project, stdin=TASK)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["labels"] == ["triage"]
    assert github.writes() == []
