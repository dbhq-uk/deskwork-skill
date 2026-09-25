import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import ids  # noqa: E402


def test_a_number_is_not_an_id():
    with pytest.raises(TypeError):
        ids.require_id(ids.IssueNumber(144))


def test_a_bare_int_is_not_an_id():
    with pytest.raises(TypeError):
        ids.require_id(144)


def test_an_id_passes():
    assert ids.require_id(ids.IssueId(3527190001)) == 3527190001


def test_resolve_turns_a_number_into_the_database_id(fake_gh):
    fake_gh({"api repos/owner/repo/issues/144": {"stdout": '{"id": 3527190001, "number": 144}'}})
    ref = ids.Ref("owner", "repo", ids.IssueNumber(144))
    assert ids.resolve(ref) == ids.IssueId(3527190001)


def test_resolve_refuses_a_mismatched_response(fake_gh):
    fake_gh({"api repos/owner/repo/issues/144": {"stdout": '{"id": 3527190001, "number": 7}'}})
    ref = ids.Ref("owner", "repo", ids.IssueNumber(144))
    with pytest.raises(ids.MismatchedIssue):
        ids.resolve(ref)
