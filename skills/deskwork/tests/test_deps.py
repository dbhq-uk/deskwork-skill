import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import deps  # noqa: E402
import ids  # noqa: E402
from test_gh import fake_gh  # noqa: E402,F401

REF = ids.Ref("owner", "repo", ids.IssueNumber(144))
BLOCKER = ids.Ref("owner", "repo", ids.IssueNumber(143))

BLOCKER_JSON = '{"id": 3527190001, "number": 143, "repository_url": "https://api.github.com/repos/owner/repo"}'


def test_blocked_by_lists_refs(fake_gh):  # noqa: F811
    fake_gh({
        "api repos/owner/repo/issues/144/dependencies/blocked_by":
            {"stdout": f"[{BLOCKER_JSON}]"},
    })
    assert deps.blocked_by(REF) == [BLOCKER]


def test_add_resolves_the_number_to_a_database_id_then_reads_back(fake_gh):  # noqa: F811
    fake_gh({
        "api repos/owner/repo/issues/143": {"stdout": BLOCKER_JSON},
        "api repos/owner/repo/issues/144/dependencies/blocked_by -X POST --input -":
            {"stdout": "{}"},
        "api repos/owner/repo/issues/144/dependencies/blocked_by":
            {"stdout": f"[{BLOCKER_JSON}]"},
    })
    deps.add_blocked_by(REF, BLOCKER)  # must not raise


def test_add_raises_when_the_edge_is_not_there_afterwards(fake_gh):  # noqa: F811
    fake_gh({
        "api repos/owner/repo/issues/143": {"stdout": BLOCKER_JSON},
        "api repos/owner/repo/issues/144/dependencies/blocked_by -X POST --input -":
            {"stdout": "{}"},
        "api repos/owner/repo/issues/144/dependencies/blocked_by": {"stdout": "[]"},
    })
    with pytest.raises(deps.WriteNotConfirmed):
        deps.add_blocked_by(REF, BLOCKER)
