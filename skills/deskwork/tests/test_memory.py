import pytest

import ids
import memory

REF = ids.Ref("owner", "repo", ids.IssueNumber(144))
BLOCKER = ids.Ref("owner", "repo", ids.IssueNumber(143))
OTHER = ids.Ref("owner", "repo", ids.IssueNumber(99))


def test_round_trips_through_the_comment_body():
    mem = memory.Memory()
    mem.record("rejected", BLOCKER, "not related")
    body = memory.render(mem)
    assert "<!-- deskwork -->" in body
    assert memory.parse(body).decisions == {BLOCKER: ("rejected", "not related")}


def test_a_comment_without_the_marker_is_ignored():
    assert memory.parse("just a normal comment").decisions == {}


@pytest.mark.parametrize("kind", memory.KINDS)
def test_every_kind_round_trips(kind):
    mem = memory.Memory()
    mem.record(kind, BLOCKER, "because")
    assert memory.parse(memory.render(mem)).decisions == {BLOCKER: (kind, "because")}


def test_a_later_decision_about_the_same_edge_replaces_the_earlier_one():
    mem = memory.Memory()
    mem.record("rejected", BLOCKER, "not yet")
    mem.record("linked", BLOCKER, "now it is")
    assert mem.decisions == {BLOCKER: ("linked", "now it is")}
    assert mem.rejected_additions == set()


def test_a_reason_on_several_lines_is_kept_on_one():
    mem = memory.Memory()
    mem.record("linked", BLOCKER, "first line\nsecond line")
    assert memory.parse(memory.render(mem)).decisions[BLOCKER] == ("linked", "first line second line")


def test_rejected_and_deliberate_are_kept_apart():
    mem = memory.Memory()
    mem.record("rejected", BLOCKER, "")
    mem.record("deliberate", OTHER, "")
    parsed = memory.parse(memory.render(mem))
    assert parsed.rejected_additions == {BLOCKER}
    assert parsed.deliberate_edges == {OTHER}


def test_the_old_format_still_parses():
    body = "<!-- deskwork -->\n- rejected: owner/repo#77 (agreed with Sam on Tuesday)\n"
    ref = ids.Ref("owner", "repo", ids.IssueNumber(77))
    assert memory.parse(body).decisions == {ref: ("rejected", "(agreed with Sam on Tuesday)")}


def test_all_human_content_survives_parse_and_render():
    body = ("<!-- deskwork -->\n"
            "- rejected: owner/repo#77 (agreed with Sam on Tuesday)\n"
            "\n## somebody's own heading\n"
            "free text nobody should lose\n")
    parsed = memory.parse(body)
    rendered = memory.render(parsed)
    for kept in ("(agreed with Sam on Tuesday)", "## somebody's own heading", "free text nobody should lose"):
        assert kept in rendered


def test_the_marker_past_the_thirtieth_comment_is_found_and_edited_in_place(github):
    marker = memory.render(memory.Memory())
    comments = [{"id": n, "body": f"comment {n}"} for n in range(1, 31)]
    comments.append({"id": 31, "body": marker})
    github.issue(144, comments=comments)
    github.issue(143)
    memory.record(REF, "rejected", BLOCKER, "not related")
    after = github.comments(144)
    assert len(after) == 31  # no second marker comment
    assert sum(memory.MARKER in c["body"] for c in after) == 1
    assert "- rejected: owner/repo#143 not related" in after[30]["body"]


def test_the_first_decision_posts_one_comment_and_reads_it_back(github):
    github.issue(144)
    memory.record(REF, "linked", BLOCKER, "the schema lands first")
    (comment,) = github.comments(144)
    assert "- linked: owner/repo#143 the schema lands first" in comment["body"]
    reads = [c["argv"] for c in github.calls if c["argv"][:2] == ["api", f"repos/owner/repo/issues/comments/{comment['id']}"]]
    assert reads, "the comment was not read back"


def test_a_comment_edit_that_does_not_stick_is_reported(github):
    github.issue(144, comments=[{"id": 5, "body": memory.render(memory.Memory())}])
    github.fault(drop_comment_edits=True)
    with pytest.raises(memory.WriteNotConfirmed):
        memory.record(REF, "rejected", BLOCKER, "not related")
