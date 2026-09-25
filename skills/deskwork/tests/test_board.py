import json

import pytest

import board
import gh
import ids

PROJECT = "PVT_kwDOABCD1234"


def test_add_item_requires_a_node_id():
    with pytest.raises(TypeError):
        board.add_item(PROJECT, ids.IssueNumber(144))


def test_add_item_refuses_a_bare_string():
    with pytest.raises(TypeError):
        board.add_item(PROJECT, "I_kwDOAbc123")


@pytest.mark.parametrize("item", [
    ids.NodeId("I_kwDOAbc123"),    # the issue's own id: the old bug
    "PVTI_lADOABCD1234",            # right shape, untyped
    ids.ItemId("I_kwDOAbc123"),    # typed, wrong shape
    ids.IssueNumber(144),
])
def test_set_field_takes_only_a_project_item_id(item):
    with pytest.raises(TypeError):
        board.set_field(PROJECT, item, "PVTSSF_status", "opt_triage")


def test_missing_project_scope_is_reported_plainly(monkeypatch):
    def boom(*args, **kwargs):
        raise gh.GhError("your authentication token is missing required scopes [read:project]")
    monkeypatch.setattr(gh, "graphql", boom)
    with pytest.raises(board.MissingScope) as caught:
        board.fields(PROJECT)
    assert "gh auth refresh -s project" in str(caught.value)


def test_add_item_returns_the_item_id(github):
    github.issue(144)
    item = board.add_item(PROJECT, ids.node_id(ids.Ref("owner", "repo", ids.IssueNumber(144))))
    assert isinstance(item, ids.ItemId) and item.startswith("PVTI_")


def test_items_follows_every_page(github):
    for n in range(1, 102):
        github.issue(n, board_status="Todo")
    github.state["board"]["drafts"] = 3
    github.save()
    found = board.items(PROJECT)
    assert len(found) == 101  # drafts are skipped
    assert {ref.number for ref, _, _ in found} == set(range(1, 102))


def test_set_status_uses_the_item_id_and_reads_back(github):
    github.issue(144)
    item = board.add_item(PROJECT, ids.node_id(ids.Ref("owner", "repo", ids.IssueNumber(144))))
    board.set_status(PROJECT, item, "Triage")
    assert github.load()["issues"]["owner/repo#144"]["board_status"] == "Triage"


def test_set_status_names_the_board_when_the_option_is_missing(github):
    github.state["board"]["options"] = [o for o in github.state["board"]["options"] if o["name"] != "Triage"]
    github.save()
    github.issue(144)
    item = board.add_item(PROJECT, ids.node_id(ids.Ref("owner", "repo", ids.IssueNumber(144))))
    with pytest.raises(board.NotConfirmed) as caught:
        board.set_status(PROJECT, item, "Triage")
    assert "Board" in str(caught.value) and PROJECT in str(caught.value) and "'Triage'" in str(caught.value)


def test_a_status_that_does_not_stick_is_not_confirmed(github):
    github.issue(144)
    github.fault(drop_status=True)
    item = board.add_item(PROJECT, ids.node_id(ids.Ref("owner", "repo", ids.IssueNumber(144))))
    with pytest.raises(board.NotConfirmed):
        board.set_status(PROJECT, item, "Triage")


def test_adding_the_triage_option_sends_json_objects_and_keeps_every_existing_option(github):
    github.state["board"]["options"] = [o for o in github.state["board"]["options"] if o["name"] != "Triage"]
    github.save()
    github.issue(1, board_status="Todo")
    github.issue(2, board_status="Done")
    assert board.ensure_status_option(PROJECT, "Triage") is True

    (call,) = [c for c in github.calls if "mutation DeskworkAddOption" in c["stdin"]]
    sent = json.loads(call["stdin"])["variables"]["options"]
    assert all(isinstance(o, dict) and {"name", "color", "description"} <= set(o) for o in sent)
    assert [o.get("id") for o in sent] == ["opt_todo", "opt_done", None]
    state = github.load()
    assert [o["name"] for o in state["board"]["options"]] == ["Todo", "Done", "Triage"]
    assert state["issues"]["owner/repo#1"]["board_status"] == "Todo"  # nobody lost a status
    assert state["issues"]["owner/repo#2"]["board_status"] == "Done"


def test_an_option_already_there_is_not_added_again(github):
    assert board.ensure_status_option(PROJECT, "Triage") is False
    assert github.writes() == []
