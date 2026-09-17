import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import ids  # noqa: E402
import issues  # noqa: E402
from test_gh import fake_gh  # noqa: E402,F401

TYPES_QUERY = (
    "api graphql -f query={ organization(login:\"owner\"){ issueTypes(first:20)"
    "{ nodes{ name isEnabled } } } }"
)


def test_org_issue_types_lists_enabled_names_only(fake_gh):  # noqa: F811
    fake_gh({TYPES_QUERY: {"stdout": (
        '{"data":{"organization":{"issueTypes":{"nodes":['
        '{"name":"Task","isEnabled":true},'
        '{"name":"Epic","isEnabled":false}]}}}}'
    )}})
    assert issues.org_issue_types("owner") == ["Task"]


def test_search_similar_returns_candidates(fake_gh):  # noqa: F811
    fake_gh({
        'api search/issues?q=repo:owner/repo+is:issue+is:open+retry+logic':
            {"stdout": '{"items":[{"number":12,"title":"retry logic drops attempts"}]}'},
    })
    found = issues.search_similar("owner", "repo", "retry logic")
    assert found[0]["number"] == 12


def test_search_similar_percent_encodes_punctuation_in_terms(fake_gh):  # noqa: F811
    # "&", "#" and "+" all mean something in a URL - unescaped, "&" starts a
    # new query parameter, "#" truncates the rest as a fragment, and "+"
    # reads as an extra encoded space. A title carrying any of them must not
    # corrupt the search terms either side of it.
    fake_gh({
        "api search/issues?q=repo:owner/repo+is:issue+is:open+"
        "fix+c%2B%2B+crash+%26+save+%23123":
            {"stdout": '{"items":[]}'},
    })
    found = issues.search_similar("owner", "repo", "Fix C++ crash & save #123")
    assert found == []


def test_search_similar_keeps_short_distinctive_words_and_drops_stop_words(fake_gh):  # noqa: F811
    # "CSP" is three characters and the whole reason the title is worth
    # finding; "is", "on" and "the" carry no search signal at any length.
    # A length cutoff keeps this backwards - it would drop "csp" and keep
    # "wrong". Stop-word filtering keeps "csp" and drops the filler.
    fake_gh({
        "api search/issues?q=repo:owner/repo+is:issue+is:open+csp+wrong+apex":
            {"stdout": '{"items":[{"number":7,"title":"CSP is wrong on the apex"}]}'},
    })
    found = issues.search_similar("owner", "repo", "CSP is wrong on the apex")
    assert found[0]["number"] == 7


def test_search_similar_falls_back_to_every_word_when_all_are_stop_words(fake_gh):  # noqa: F811
    # A title built entirely from stop words must still produce a usable
    # search rather than an empty query string. If the fallback did not
    # fire, the built path would not match this canned response and fake_gh
    # would exit non-zero, failing the test loudly.
    fake_gh({
        "api search/issues?q=repo:owner/repo+is:issue+is:open+is+it+to+be":
            {"stdout": '{"items":[]}'},
    })
    found = issues.search_similar("owner", "repo", "Is it to be")
    assert found == []


def test_create_uses_the_rest_endpoint_because_gh_issue_create_has_no_type(fake_gh):  # noqa: F811
    fake_gh({
        "api repos/owner/repo/issues -X POST --input -":
            {"stdout": '{"number": 145, "id": 999}'},
    })
    ref = issues.create("owner", "repo", "Title", "Body", "Bug", ["area:infra"])
    assert ref == ids.Ref("owner", "repo", ids.IssueNumber(145))


def test_create_without_issue_type_omits_type_from_the_payload(monkeypatch):
    captured = {}

    def fake_api(path, method="GET", body=None):
        captured["path"] = path
        captured["method"] = method
        captured["body"] = body
        return {"number": 7}

    monkeypatch.setattr(issues.gh, "api", fake_api)
    ref = issues.create("owner", "repo", "Title", "Body", None, [])
    assert "type" not in captured["body"]
    assert ref == ids.Ref("owner", "repo", ids.IssueNumber(7))


def test_create_coerces_labels_to_a_list(monkeypatch):
    captured = {}

    def fake_api(path, method="GET", body=None):
        captured["body"] = body
        return {"number": 9}

    monkeypatch.setattr(issues.gh, "api", fake_api)
    issues.create("owner", "repo", "Title", "Body", "Task", ("area:infra", "area:web"))
    assert captured["body"]["labels"] == ["area:infra", "area:web"]


def test_body_for_a_bug_carries_the_required_sections():
    body = issues.body_for(
        "Bug",
        context="Seen while changing the upload path.",
        expected="The last attempt is retried.",
        actual="The last attempt is dropped.",
        acceptance="A test covers the final attempt.",
    )
    for heading in ("Context", "Expected", "Actual", "Acceptance"):
        assert f"**{heading}**" in body


def test_body_for_a_feature_carries_the_required_sections():
    body = issues.body_for(
        "Feature",
        context="No way to export a report today.",
        proposal="Add a CSV export button.",
        acceptance="Exporting produces a valid CSV with a header row.",
        out_of_scope="Scheduled/automatic export.",
    )
    for heading in ("Context", "Proposal", "Acceptance", "Out of scope"):
        assert f"**{heading}**" in body


def test_body_for_defaults_to_task_sections_for_an_unknown_kind():
    body = issues.body_for("Chore", context="Tidying.", acceptance="Done.")
    assert "**Context**" in body
    assert "**Acceptance**" in body
    assert "**Expected**" not in body


def test_body_for_marks_a_missing_section_as_not_stated():
    body = issues.body_for("Task", context="Only context given.")
    assert "_not stated_" in body
