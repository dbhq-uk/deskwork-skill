import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import board  # noqa: E402
import gh  # noqa: E402
import ids  # noqa: E402
from test_gh import fake_gh  # noqa: E402,F401


def test_add_item_requires_a_node_id():
    with pytest.raises(TypeError):
        board.add_item("PVT_x", ids.IssueNumber(144))


def test_add_item_refuses_an_issue_id():
    with pytest.raises(TypeError):
        board.add_item("PVT_x", ids.IssueId(3527190001))


def test_missing_project_scope_is_reported_plainly(fake_gh, monkeypatch):  # noqa: F811
    def boom(*args, **kwargs):
        raise gh.GhError("your authentication token is missing required scopes [read:project]")
    monkeypatch.setattr(gh, "graphql", boom)
    with pytest.raises(board.MissingScope) as caught:
        board.fields("PVT_x")
    assert "gh auth refresh -s project" in str(caught.value)


def test_add_item_returns_the_item_id(monkeypatch):
    def mock_graphql(query, **variables):
        return {
            "addProjectV2ItemById": {
                "item": {
                    "id": "PVTI_lADOABCD1234"
                }
            }
        }
    monkeypatch.setattr(gh, "graphql", mock_graphql)
    item_id = board.add_item(
        "PVT_kwDOABCD1234",
        ids.NodeId("I_kwDOAbc123")
    )
    assert item_id == "PVTI_lADOABCD1234"


def test_fields_returns_project_fields(monkeypatch):
    def mock_graphql(query, **variables):
        return {
            "node": {
                "fields": {
                    "nodes": [
                        {
                            "id": "PVTF_x",
                            "name": "Status",
                            "options": [{"id": "opt1", "name": "Todo"}]
                        }
                    ]
                }
            }
        }
    monkeypatch.setattr(gh, "graphql", mock_graphql)
    fields_result = board.fields("PVT_kwDOABCD1234")
    assert "Status" in fields_result
    assert fields_result["Status"]["id"] == "PVTF_x"


def test_items_returns_project_items(monkeypatch):
    def mock_graphql(query, **variables):
        return {
            "node": {
                "items": {
                    "nodes": [
                        {
                            "id": "PVTI_x",
                            "content": {
                                "number": 144,
                                "repository": {"name": "test", "owner": {"login": "owner"}},
                                "state": "OPEN"
                            }
                        }
                    ]
                }
            }
        }
    monkeypatch.setattr(gh, "graphql", mock_graphql)
    items_result = board.items("PVT_kwDOABCD1234")
    assert len(items_result) == 1
    assert items_result[0]["id"] == "PVTI_x"


def test_missing_scope_message_includes_fix():
    """Test that MissingScope messages are helpful."""
    exc = board.MissingScope("Projects v2 needs the project scope, which this token does not have. Run: gh auth refresh -s project")
    assert "gh auth refresh -s project" in str(exc)
