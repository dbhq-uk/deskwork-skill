"""Edges go through gh issue edit and are read back. See also test_edges.py."""
import pytest

import deps
import ids

REF = ids.Ref("owner", "repo", ids.IssueNumber(144))
BLOCKER = ids.Ref("owner", "repo", ids.IssueNumber(143))
CROSS = ids.Ref("other", "lib", ids.IssueNumber(143))


def test_blocked_by_lists_every_blocker_with_its_state(github):
    github.issue(143, "Local", state="CLOSED")
    github.issue(143, "Elsewhere", repo="other/lib")
    github.issue(144, blocked_by=[143, "other/lib#143"])
    found = deps.blocked_by(REF)
    assert [(b.ref, b.state) for b in found] == [(BLOCKER, "CLOSED"), (CROSS, "OPEN")]


def test_more_than_thirty_blockers_all_come_back(github):
    for n in range(1, 32):
        github.issue(n)
    github.issue(144, blocked_by=range(1, 32))
    assert len(deps.blocked_by(REF)) == 31


def test_link_writes_through_gh_issue_edit_and_reads_back(github):
    github.issue(143)
    github.issue(144)
    assert deps.link(REF, BLOCKER) is True
    assert github.blockers(144) == ["owner/repo#143"]
    argv = [c["argv"] for c in github.calls]
    edit = argv.index(["issue", "edit", "144", "-R", "owner/repo", "--add-blocked-by", "143"])
    assert argv[edit + 1][:3] == ["issue", "view", "144"]  # the read-back


def test_a_cross_repo_blocker_is_named_by_url(github):
    github.issue(143, repo="other/lib")
    github.issue(144)
    deps.link(REF, CROSS)
    assert github.blockers(144) == ["other/lib#143"]
    assert ["issue", "edit", "144", "-R", "owner/repo", "--add-blocked-by",
            "https://github.com/other/lib/issues/143"] in [c["argv"] for c in github.calls]


def test_a_link_that_lands_on_a_different_issue_names_it_and_how_to_remove_it(github):
    # The failure the old REST path allowed: success reported, wrong issue linked.
    github.issue(143)
    github.issue(144)
    github.issue(99, repo="other/lib")
    github.fault(link_instead="other/lib#99")
    with pytest.raises(deps.WriteNotConfirmed) as caught:
        deps.link(REF, BLOCKER)
    message = str(caught.value)
    assert "other/lib#99" in message
    assert ("gh issue edit 144 -R owner/repo --remove-blocked-by "
            "https://github.com/other/lib/issues/99") in message


def test_a_link_that_does_not_land_is_not_confirmed(github):
    github.issue(143)
    github.issue(144)
    github.fault(ignore_edits=True)
    with pytest.raises(deps.WriteNotConfirmed):
        deps.link(REF, BLOCKER)


def test_an_existing_edge_is_not_written_again(github):
    github.issue(143)
    github.issue(144, blocked_by=[143])
    assert deps.link(REF, BLOCKER) is False
    assert github.writes() == []


def test_unlink_removes_and_reads_back(github):
    github.issue(143)
    github.issue(144, blocked_by=[143])
    assert deps.unlink(REF, BLOCKER) is True
    assert github.blockers(144) == []


def test_an_unlink_that_does_not_land_is_not_confirmed(github):
    github.issue(143)
    github.issue(144, blocked_by=[143])
    github.fault(ignore_edits=True)
    with pytest.raises(deps.WriteNotConfirmed) as caught:
        deps.unlink(REF, BLOCKER)
    assert "still is" in str(caught.value)


def test_no_script_can_reach_the_database_id_api():
    import pathlib
    scripts = pathlib.Path(deps.__file__).parent
    for path in scripts.glob("*.py"):
        text = path.read_text()
        assert "dependencies/blocked_by" not in text, path.name
        assert "issue_id" not in text, path.name
