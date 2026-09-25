import datetime

import pytest

import ids
import issues

NOW = datetime.datetime(2026, 9, 25, 12, 0, tzinfo=datetime.timezone.utc)


@pytest.mark.parametrize("kind, headings", [
    ("Bug", ["Context", "Expected", "Actual", "Acceptance"]),
    ("Feature", ["Context", "Proposal", "Acceptance", "Out of scope"]),
    ("Task", ["Context", "Acceptance"]),
])
def test_each_type_has_its_own_sections(kind, headings):
    body = issues.body_for(kind)
    assert [line[2:-2] for line in body.splitlines() if line.startswith("**")] == headings


def test_an_unknown_type_gets_task_sections():
    assert "**Expected**" not in issues.body_for("Chore")


def test_a_filled_body_passes():
    body = issues.body_for("Bug", context="c", expected="e", actual="a", acceptance="x")
    assert issues.body_problems("Bug", body) == []


def test_a_body_still_saying_not_stated_is_refused():
    problems = issues.body_problems("Task", issues.body_for("Task", context="Only context."))
    assert any("_not stated_" in p for p in problems)


def test_a_bug_without_expected_and_actual_is_refused():
    problems = issues.body_problems("Bug", "**Context**\n\nc\n\n**Acceptance**\n\nx")
    assert len(problems) == 2 and "Expected" in problems[0] and "Actual" in problems[1]


def test_markdown_headings_count_as_sections():
    assert issues.body_problems("Task", "## Context\nc\n### Acceptance\nx") == []


def test_similarity_ignores_word_order_filler_and_tense():
    assert issues.similarity("Retry logic drops the last attempt",
                             "Last attempt dropped by retry logic") == 1.0


def test_short_distinctive_words_are_kept():
    assert "csp" in issues.tokens("CSP is wrong on the apex")
    assert "is" not in issues.tokens("CSP is wrong on the apex")


def _candidates(github, title):
    return issues.duplicate_candidates("owner", "repo", title, now=NOW)


def test_a_reworded_open_duplicate_is_found_by_title_overlap(github):
    github.issue(12, "Retry logic drops the last attempt")
    github.issue(13, "Unrelated work on exports")
    found, warning = _candidates(github, "Last attempt is dropped by the retry logic")
    assert [c["ref"] for c in found] == ["#12"] and warning is None
    assert found[0]["found_by"] == "title overlap"


def test_a_duplicate_closed_in_the_last_thirty_days_is_found_by_search(github):
    github.issue(20, "Uploads time out on slow links", state="CLOSED", closed_at="2026-09-15T10:00:00Z")
    github.issue(21, "Old timeout problem", state="CLOSED", closed_at="2026-08-01T10:00:00Z")
    github.set(search_hits=["owner/repo#20", "owner/repo#21"])
    found, _ = _candidates(github, "Large files fail over a poor connection")
    assert [(c["ref"], c["state"]) for c in found] == [("#20", "CLOSED")]


def test_search_asks_for_hybrid_results(github):
    _candidates(github, "Anything")
    (search,) = [c["argv"] for c in github.calls if c["argv"][:2] == ["api", "search/issues"]]
    assert "search_type=hybrid" in search and "-X" in search and "GET" in search


def test_a_search_failure_is_a_warning_and_title_overlap_still_runs(github):
    github.issue(12, "Retry logic drops the last attempt")
    github.fault(search_down=True)
    found, warning = _candidates(github, "Retry logic drops the last attempt")
    assert [c["ref"] for c in found] == ["#12"]
    assert "hybrid search failed" in warning


def test_nothing_similar_means_no_candidates(github):
    github.issue(12, "Retry logic drops the last attempt")
    assert _candidates(github, "Add a dark theme to the settings page") == ([], None)


def test_create_goes_through_gh_issue_create_with_every_flag(github):
    github.issue(5)
    github.issue(9, repo="other/lib")
    parent = ids.Ref("owner", "repo", ids.IssueNumber(5))
    blocker = ids.Ref("other", "lib", ids.IssueNumber(9))
    ref = issues.create("owner", "repo", "Title", "**Context**\n\nc", "Bug", ["triage", "area:infra"],
                        parent=parent, blocked_by=[blocker])
    assert ref == ids.Ref("owner", "repo", ids.IssueNumber(6))
    (argv,) = [c["argv"] for c in github.calls if c["argv"][:2] == ["issue", "create"]]
    assert argv == ["issue", "create", "-R", "owner/repo", "--title", "Title", "--body-file", "-",
                    "--label", "triage", "--label", "area:infra", "--type", "Bug",
                    "--parent", "5", "--blocked-by", "https://github.com/other/lib/issues/9"]
    node, problems = issues.check_filed(ref, "Title", "**Context**\n\nc", "Bug",
                                        ["triage", "area:infra"], parent, [blocker])
    assert problems == [] and node.startswith("I_")
