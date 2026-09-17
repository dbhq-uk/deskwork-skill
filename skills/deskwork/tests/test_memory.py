import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import ids  # noqa: E402
import memory  # noqa: E402

REF = ids.Ref("owner", "repo", ids.IssueNumber(144))
BLOCKER = ids.Ref("owner", "repo", ids.IssueNumber(143))


def test_round_trips_through_the_comment_body():
    body = memory.render(
        memory.Memory(rejected_additions={BLOCKER}, deliberate_edges=set())
    )
    assert "<!-- deskwork -->" in body
    parsed = memory.parse(body)
    assert parsed.rejected_additions == {BLOCKER}


def test_a_comment_without_the_marker_is_ignored():
    assert memory.parse("just a normal comment").rejected_additions == set()


def test_both_directions_are_kept_apart():
    original = memory.Memory(
        rejected_additions={BLOCKER},
        deliberate_edges={ids.Ref("owner", "repo", ids.IssueNumber(99))},
    )
    parsed = memory.parse(memory.render(original))
    assert parsed.rejected_additions == original.rejected_additions
    assert parsed.deliberate_edges == original.deliberate_edges
