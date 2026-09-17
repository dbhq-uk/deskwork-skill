import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import deps  # noqa: E402
import ids  # noqa: E402
from test_gh import fake_gh  # noqa: E402,F401

REF = ids.Ref("owner", "repo", ids.IssueNumber(144))
BLOCKER = ids.Ref("owner", "repo", ids.IssueNumber(143))
CROSS_BLOCKER = ids.Ref("other-owner", "other-repo", ids.IssueNumber(143))

BLOCKER_JSON = '{"id": 3527190001, "number": 143, "repository_url": "https://api.github.com/repos/owner/repo"}'
CROSS_BLOCKER_JSON = (
    '{"id": 3527190002, "number": 143, '
    '"repository_url": "https://api.github.com/repos/other-owner/other-repo"}'
)


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


def test_add_resolves_a_cross_repo_blocker_against_its_own_repo(fake_gh):  # noqa: F811
    # Canned responses are keyed on the blocker's own repo (other-owner/other-repo).
    # If a future change ever resolved the blocker against ref's repo (owner/repo)
    # instead, that lookup would miss the canned response and fake_gh would exit
    # non-zero, so this test fails loudly rather than silently linking the wrong repo.
    fake_gh({
        "api repos/other-owner/other-repo/issues/143": {"stdout": CROSS_BLOCKER_JSON},
        "api repos/owner/repo/issues/144/dependencies/blocked_by -X POST --input -":
            {"stdout": "{}"},
        "api repos/owner/repo/issues/144/dependencies/blocked_by":
            {"stdout": f"[{CROSS_BLOCKER_JSON}]"},
    })
    deps.add_blocked_by(REF, CROSS_BLOCKER)  # must not raise


def test_blocking_lists_refs(fake_gh):  # noqa: F811
    fake_gh({
        "api repos/owner/repo/issues/144/dependencies/blocking":
            {"stdout": f"[{BLOCKER_JSON}]"},
    })
    assert deps.blocking(REF) == [BLOCKER]


def test_remove_raises_when_the_edge_is_still_there_afterwards(fake_gh):  # noqa: F811
    fake_gh({
        "api repos/owner/repo/issues/143": {"stdout": BLOCKER_JSON},
        "api repos/owner/repo/issues/144/dependencies/blocked_by/3527190001 -X DELETE":
            {"stdout": "{}"},
        "api repos/owner/repo/issues/144/dependencies/blocked_by":
            {"stdout": f"[{BLOCKER_JSON}]"},
    })
    with pytest.raises(deps.WriteNotConfirmed):
        deps.remove_blocked_by(REF, BLOCKER)


def test_ref_from_issue_raises_loudly_on_unexpected_repository_url_shape(fake_gh):  # noqa: F811
    # An extra trailing segment after the repo name used to make rsplit("/", 2)
    # silently pick the wrong two segments as owner/repo. It must now raise
    # instead of returning a plausible-looking but wrong Ref.
    malformed = (
        '{"id": 3527190001, "number": 143, '
        '"repository_url": "https://api.github.com/repos/owner/repo/issues/143"}'
    )
    fake_gh({
        "api repos/owner/repo/issues/144/dependencies/blocked_by":
            {"stdout": f"[{malformed}]"},
    })
    with pytest.raises(ValueError):
        deps.blocked_by(REF)
