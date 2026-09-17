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


def test_a_line_with_a_trailing_note_round_trips_with_the_note_intact():
    original = memory.Memory(rejected_additions={BLOCKER}, deliberate_edges=set())
    original._notes[BLOCKER] = "(agreed with Sam on Tuesday)"
    body = memory.render(original)
    assert "(agreed with Sam on Tuesday)" in body
    parsed = memory.parse(body)
    assert parsed.rejected_additions == {BLOCKER}
    assert parsed._notes.get(BLOCKER) == "(agreed with Sam on Tuesday)"


def test_an_unparseable_line_survives_a_parse_and_render_cycle():
    unparseable_line = "- invalid line that doesn't match the pattern"
    body = (
        f"{memory.MARKER}\n\n"
        f"**deskwork** is remembering these decisions, so it stops asking.\n\n"
        f"{unparseable_line}"
    )
    parsed = memory.parse(body)
    assert unparseable_line in parsed.unparseable_lines
    rendered = memory.render(parsed)
    assert unparseable_line in rendered
