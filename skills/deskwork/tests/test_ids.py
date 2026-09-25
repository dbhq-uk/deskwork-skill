import pytest

import ids

HOME = ("owner", "repo")


def test_there_is_no_database_id_type_left_to_misuse():
    # The dependencies REST API took a database id and linked the wrong issue
    # when given a number. Edges now go through gh issue edit, which takes the
    # number, so neither the type nor the resolver should exist.
    assert not hasattr(ids, "IssueId")
    assert not hasattr(ids, "resolve")


def test_a_bare_string_is_not_a_node_id():
    with pytest.raises(TypeError):
        ids.require_node_id("I_kwDOAbc123")


def test_a_number_is_not_a_node_id():
    with pytest.raises(TypeError):
        ids.require_node_id(ids.IssueNumber(144))


def test_a_node_id_passes():
    assert ids.require_node_id(ids.NodeId("I_kwDOAbc123")) == "I_kwDOAbc123"


def test_node_id_asks_gh_and_checks_the_number(fake_gh):
    fake_gh({"issue view 144 -R owner/repo --json id,number":
             {"stdout": '{"id": "I_kwDOAbc123", "number": 144}'}})
    found = ids.node_id(ids.Ref("owner", "repo", ids.IssueNumber(144)))
    assert found == "I_kwDOAbc123" and isinstance(found, ids.NodeId)


def test_node_id_refuses_a_mismatched_response(fake_gh):
    fake_gh({"issue view 144 -R owner/repo --json id,number":
             {"stdout": '{"id": "I_kwDOAbc123", "number": 7}'}})
    with pytest.raises(ids.MismatchedIssue):
        ids.node_id(ids.Ref("owner", "repo", ids.IssueNumber(144)))


@pytest.mark.parametrize("text, expected", [
    ("12", ids.Ref("owner", "repo", ids.IssueNumber(12))),
    ("#12", ids.Ref("owner", "repo", ids.IssueNumber(12))),
    (12, ids.Ref("owner", "repo", ids.IssueNumber(12))),
    ("other/lib#99", ids.Ref("other", "lib", ids.IssueNumber(99))),
    ("https://github.com/other/lib/issues/99", ids.Ref("other", "lib", ids.IssueNumber(99))),
])
def test_references_parse(text, expected):
    assert ids.parse(text, HOME) == expected


@pytest.mark.parametrize("text", ["", "twelve", "#", "owner/repo", "12a"])
def test_a_bad_reference_is_an_error(text):
    with pytest.raises(ValueError):
        ids.parse(text, HOME)


def test_gh_is_given_a_number_at_home_and_a_url_elsewhere():
    assert ids.Ref("owner", "repo", ids.IssueNumber(5)).gh_arg(HOME) == "5"
    assert ids.Ref("other", "lib", ids.IssueNumber(5)).gh_arg(HOME) == "https://github.com/other/lib/issues/5"


def test_short_form_depends_on_home():
    assert ids.Ref("owner", "repo", ids.IssueNumber(5)).short(HOME) == "#5"
    assert ids.Ref("other", "lib", ids.IssueNumber(5)).short(HOME) == "other/lib#5"
