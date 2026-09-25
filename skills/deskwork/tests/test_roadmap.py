import datetime

import pytest

import graph
import ids
import roadmap

HOME = ("owner", "repo")


def ref(n, owner="owner", repo="repo"):
    return ids.Ref(owner, repo, ids.IssueNumber(n))


def build(**overrides):
    args = dict(
        home=HOME,
        generated=datetime.date(2026, 9, 17),
        issue_count=4,
        order=[(ref(143), "Nothing blocks it, and #144 cannot start until it lands.")],
        blocked=[(ref(144), [ref(143)])],
        later=[ref(145)],
        triage=[ref(146)],
        graph=graph.Graph({ref(144): {ref(143)}, ref(143): set()}),
        titles={ref(143): "Register drift", ref(144): "Positioning changed",
                ref(145): "Tidy", ref(146): "Found while testing"},
    )
    args.update(overrides)
    return roadmap.render(**args)


def test_it_states_when_and_from_what():
    text = build()
    assert "2026-09-17" in text and "4 open issues" in text


def test_the_order_is_kept_and_each_reason_sits_under_its_item():
    text = build(order=[(ref(145), "Small and unblocks review."), (ref(143), "Then the drift.")], later=[])
    lines = text.splitlines()
    first = lines.index("1. **#145** Tidy")
    assert lines[first + 1] == "   Why: Small and unblocks review."
    second = lines.index("2. **#143** Register drift")
    assert lines[second + 1] == "   Why: Then the drift."


def test_the_headings_buildwork_reads_are_exact():
    text = build()
    for heading in ("## Next", "## Blocked", "## Triage"):
        assert heading in text.splitlines()


def test_a_blocked_item_shows_its_blocker():
    assert "- **#144** Positioning changed - blocked by #143" in build()


def test_triage_is_listed_last_and_never_numbered():
    text = build()
    assert text.index("## Triage") > text.index("## Next")
    assert "- **#146** Found while testing" in text


def test_nothing_ordered_is_said_plainly():
    assert "Nothing is ordered yet." in build(order=[])


def test_no_em_dashes():
    # Escapes, not the literal characters: CI greps every file for them,
    # including this one, so a literal here fails the build it protects.
    assert "\u2014" not in build() and "\u2013" not in build()


def test_cross_repo_references_keep_their_repository():
    text = build(blocked=[(ref(1), [ref(99, "other", "lib")])], order=[], later=[], triage=[],
                 titles={ref(1): "First task"},
                 graph=graph.Graph({ref(1): {ref(99, "other", "lib")}}))
    assert "- **#1** First task - blocked by other/lib#99" in text


def test_load_order_reads_refs_and_reasons():
    entries, problems = roadmap.load_order('[{"ref": "#12", "reason": "first"}, {"ref": 7, "reason": "then"}]', HOME)
    assert entries == [(ref(12), "first"), (ref(7), "then")] and problems == []


@pytest.mark.parametrize("text", ["not json", '{"ref": "#1"}'])
def test_an_unreadable_order_is_an_error(text):
    with pytest.raises(roadmap.OrderError):
        roadmap.load_order(text, HOME)


def test_entries_without_a_ref_are_problems():
    entries, problems = roadmap.load_order('[{"reason": "x"}, {"ref": "nope", "reason": "y"}]', HOME)
    assert entries == [] and len(problems) == 2
