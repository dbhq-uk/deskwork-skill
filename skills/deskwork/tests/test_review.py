"""review, run as the agent runs it, against a fake GitHub."""
import json

import memory
from conftest import deskwork


def test_review_json_carries_every_edge_with_its_state_the_memory_and_the_bottlenecks(project, github):
    github.issue(1, "Schema")
    github.issue(2, "Done already", state="CLOSED")
    github.issue(3, "Migration", blocked_by=[1, 2])
    github.issue(4, "Reports", blocked_by=[1])
    github.issue(5, "Exports", blocked_by=[1], labels=["triage"])
    github.issue(9, "Elsewhere", repo="other/lib")
    mem = memory.Memory()
    mem.record("rejected", github_ref(6), "unrelated")
    github.issue(6, "Docs", blocked_by=["other/lib#9"],
                 comments=[{"id": 70, "body": "a human comment"}, {"id": 71, "body": memory.render(mem)}])

    result = deskwork("review", "--json", cwd=project)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)

    issues = {i["ref"]: i for i in report["issues"]}
    assert set(issues) == {"#1", "#3", "#4", "#5", "#6"}  # closed #2 is not open
    assert issues["#3"]["blocked_by"] == [
        {"ref": "#1", "state": "OPEN", "title": "Schema"},
        {"ref": "#2", "state": "CLOSED", "title": "Done already"},
    ]
    assert issues["#6"]["blocked_by"] == [{"ref": "other/lib#9", "state": "OPEN", "title": "Elsewhere"}]
    assert issues["#6"]["memory"] == [{"decision": "rejected", "ref": "#6", "note": "unrelated"}]
    assert issues["#5"]["triage"] is True
    assert report["bottlenecks"] == [{"ref": "#1", "blocks": 3}]
    assert report["ready"] == ["#1"]
    assert report["blocked"] == ["#3", "#4", "#6"]
    assert report["triage"] == ["#5"]
    assert github.writes() == []


def github_ref(n):
    import ids
    return ids.Ref("owner", "repo", ids.IssueNumber(n))


def test_review_reports_a_cycle(project, github):
    github.issue(1, blocked_by=[2])
    github.issue(2, blocked_by=[1])
    report = json.loads(deskwork("review", "--json", cwd=project).stdout)
    assert report["cycles"] == [["#1", "#2"]]


def test_review_text_prints_the_edges_not_just_counts(project, github):
    github.issue(1, "Schema")
    github.issue(3, "Migration", blocked_by=[1])
    result = deskwork("review", cwd=project)
    assert result.returncode == 0, result.stderr
    assert "blocked by #1 (open) Schema" in result.stdout
    assert "Agent reasoning would propose" not in result.stdout


def test_review_makes_the_same_number_of_calls_for_5_issues_as_for_50(project, github):
    for n in range(1, 6):
        github.issue(n)
    deskwork("review", "--json", cwd=project)
    few = len(github.calls)
    github.state["calls"] = []
    for n in range(6, 51):
        github.issue(n, blocked_by=[n - 1])
    github.save()
    deskwork("review", "--json", cwd=project)
    assert len(github.calls) == few


def test_review_follows_pages_past_fifty_issues(project, github):
    for n in range(1, 53):
        github.issue(n)
    report = json.loads(deskwork("review", "--json", cwd=project).stdout)
    assert report["open_issues"] == 52


def test_memory_past_the_hundredth_comment_is_still_read(project, github):
    mem = memory.Memory()
    mem.record("deliberate", github_ref(1), "kept on purpose")
    comments = [{"id": n, "body": f"comment {n}"} for n in range(1, 101)]
    comments.append({"id": 101, "body": memory.render(mem)})
    github.issue(1)
    github.issue(2, blocked_by=[1], comments=comments)
    report = json.loads(deskwork("review", "--json", cwd=project).stdout)
    issue = next(i for i in report["issues"] if i["ref"] == "#2")
    assert issue["memory"] == [{"decision": "deliberate", "ref": "#1", "note": "kept on purpose"}]


def test_a_missing_project_scope_is_named(project, github):
    github.issue(1)
    github.fault(no_project_scope=True)
    result = deskwork("review", "--json", cwd=project)
    assert result.returncode == 1
    assert "gh auth refresh -s project" in result.stderr
