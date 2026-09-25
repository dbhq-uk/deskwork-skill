"""link, unlink, reject and keep, run as the agent runs them.

Each checks three things against the fake GitHub: the graph write (or that
there was none), the read-back after it, and the memory comment.
"""
import pytest

import memory
from conftest import deskwork


def _decisions(github, number):
    bodies = [c["body"] for c in github.comments(number) if memory.MARKER in c["body"]]
    assert len(bodies) <= 1, "more than one deskwork comment"
    return {str(ref): kind_note for ref, kind_note in memory.parse(bodies[0] if bodies else "").decisions.items()}


def _read_back_after(github, verb_flag):
    argv = [c["argv"] for c in github.calls]
    edits = [i for i, a in enumerate(argv) if a[:2] == ["issue", "edit"] and verb_flag in a]
    assert len(edits) == 1
    return argv[edits[0] + 1][:2] == ["issue", "view"] and "number,blockedBy" in argv[edits[0] + 1]


def test_link_writes_the_edge_reads_it_back_and_records_the_reason(project, github):
    github.issue(5, "Schema")
    github.issue(12, "Migration")
    result = deskwork("link", "12", "--blocked-by", "5", "--reason", "The migration needs the schema", cwd=project)
    assert result.returncode == 0, result.stderr
    assert github.blockers(12) == ["owner/repo#5"]
    assert _read_back_after(github, "--add-blocked-by")
    assert _decisions(github, 12) == {"owner/repo#5": ("linked", "The migration needs the schema")}
    assert "written and read back" in result.stdout


def test_unlink_removes_the_edge_reads_it_back_and_records_the_reason(project, github):
    github.issue(5)
    github.issue(12, blocked_by=[5])
    result = deskwork("unlink", "#12", "--blocked-by", "#5", "--reason", "No longer needed", cwd=project)
    assert result.returncode == 0, result.stderr
    assert github.blockers(12) == []
    assert _read_back_after(github, "--remove-blocked-by")
    assert _decisions(github, 12) == {"owner/repo#5": ("unlinked", "No longer needed")}


def test_reject_writes_nothing_to_the_graph_and_remembers(project, github):
    github.issue(5)
    github.issue(12)
    result = deskwork("reject", "12", "--blocked-by", "5", "--reason", "Different areas", cwd=project)
    assert result.returncode == 0, result.stderr
    assert github.blockers(12) == []
    assert not [w for w in github.writes() if w[:2] == ["issue", "edit"]]
    assert _decisions(github, 12) == {"owner/repo#5": ("rejected", "Different areas")}


def test_reject_refuses_an_edge_that_exists(project, github):
    github.issue(5)
    github.issue(12, blocked_by=[5])
    result = deskwork("reject", "12", "--blocked-by", "5", "--reason", "x", cwd=project)
    assert result.returncode == 1
    assert "use unlink" in result.stderr
    assert github.writes() == []


def test_keep_marks_an_existing_edge_deliberate(project, github):
    github.issue(5)
    github.issue(12, blocked_by=[5])
    result = deskwork("keep", "12", "--blocked-by", "5", "--reason", "Order matters here", cwd=project)
    assert result.returncode == 0, result.stderr
    assert github.blockers(12) == ["owner/repo#5"]
    assert _decisions(github, 12) == {"owner/repo#5": ("deliberate", "Order matters here")}


def test_a_link_that_lands_on_the_wrong_issue_is_reported_and_names_the_fix(project, github):
    github.issue(5)
    github.issue(12)
    github.issue(99, repo="other/lib")
    github.fault(link_instead="other/lib#99")
    result = deskwork("link", "12", "--blocked-by", "5", "--reason", "x", cwd=project)
    assert result.returncode == 4
    assert "other/lib#99" in result.stderr
    assert "--remove-blocked-by https://github.com/other/lib/issues/99" in result.stderr
    assert _decisions(github, 12) == {}  # nothing recorded for an edge that did not land


def test_a_cross_repo_blocker_is_linked_by_url(project, github):
    github.issue(9, repo="other/lib")
    github.issue(12)
    result = deskwork("link", "12", "--blocked-by", "other/lib#9", "--reason", "Upstream fix first", cwd=project)
    assert result.returncode == 0, result.stderr
    assert github.blockers(12) == ["other/lib#9"]


@pytest.mark.parametrize("verb", ["link", "unlink", "reject", "keep"])
def test_every_verb_needs_a_reason(project, github, verb):
    github.issue(5)
    github.issue(12)
    result = deskwork(verb, "12", "--blocked-by", "5", cwd=project)
    assert result.returncode == 1
    assert "--reason is required" in result.stderr
    assert github.writes() == []


@pytest.mark.parametrize("verb", ["link", "unlink", "reject"])
def test_dry_run_writes_nothing(project, github, verb):
    github.issue(5)
    github.issue(12, blocked_by=[5] if verb == "unlink" else [])
    result = deskwork(verb, "12", "--blocked-by", "5", "--reason", "x", "--dry-run", cwd=project)
    assert result.returncode == 0, result.stderr
    assert "would" in result.stdout
    assert github.writes() == []
