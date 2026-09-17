import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import graph  # noqa: E402
import ids  # noqa: E402


def ref(n):
    return ids.Ref("owner", "repo", ids.IssueNumber(n))


def test_ready_is_everything_with_no_blocker():
    g = graph.Graph({ref(144): {ref(143)}, ref(143): set()})
    assert g.ready() == [ref(143)]


def test_blocked_is_the_rest():
    g = graph.Graph({ref(144): {ref(143)}, ref(143): set()})
    assert g.blocked() == [ref(144)]


def test_a_cycle_is_reported_not_smoothed_over():
    g = graph.Graph({ref(1): {ref(2)}, ref(2): {ref(3)}, ref(3): {ref(1)}})
    cycles = g.cycles()
    assert len(cycles) == 1
    assert set(cycles[0]) == {ref(1), ref(2), ref(3)}


def test_bottleneck_is_anything_blocking_three_or_more():
    g = graph.Graph({
        ref(1): {ref(9)}, ref(2): {ref(9)}, ref(3): {ref(9)},
        ref(4): {ref(8)}, ref(9): set(), ref(8): set(),
    })
    assert g.bottlenecks() == [(ref(9), 3)]


def test_a_closed_blocker_is_not_a_blocker():
    g = graph.Graph({ref(144): {ref(143)}}, closed={ref(143)})
    assert g.ready() == [ref(144)]


def test_a_closed_issue_with_no_blockers_does_not_appear():
    g = graph.Graph({ref(200): set()}, closed={ref(200)})
    assert g.ready() == []
    assert g.blocked() == []


def test_a_closed_issue_that_had_an_open_blocker_does_not_appear():
    g = graph.Graph({ref(200): {ref(199)}}, closed={ref(200)})
    assert g.ready() == []
    assert g.blocked() == []


def test_a_chain_of_two_closed_issues_does_not_appear():
    g = graph.Graph({ref(200): {ref(199)}, ref(199): set()}, closed={ref(200), ref(199)})
    assert g.ready() == []
    assert g.blocked() == []


def test_bottlenecks_are_stable_across_repos():
    g = graph.Graph({
        ids.Ref("owner1", "repo1", ids.IssueNumber(123)): {ids.Ref("owner1", "repo1", ids.IssueNumber(999))},
        ids.Ref("owner1", "repo1", ids.IssueNumber(124)): {ids.Ref("owner1", "repo1", ids.IssueNumber(999))},
        ids.Ref("owner2", "repo2", ids.IssueNumber(123)): {ids.Ref("owner2", "repo2", ids.IssueNumber(999))},
        ids.Ref("owner2", "repo2", ids.IssueNumber(124)): {ids.Ref("owner2", "repo2", ids.IssueNumber(999))},
        ids.Ref("owner1", "repo1", ids.IssueNumber(999)): set(),
        ids.Ref("owner2", "repo2", ids.IssueNumber(999)): set(),
    })
    result = g.bottlenecks(threshold=2)
    assert len(result) == 2
    assert result == [
        (ids.Ref("owner1", "repo1", ids.IssueNumber(999)), 2),
        (ids.Ref("owner2", "repo2", ids.IssueNumber(999)), 2),
    ]


def test_cycles_output_is_stable_regardless_of_insertion_order():
    edges_order1 = {
        ref(1): {ref(2)},
        ref(2): {ref(3)},
        ref(3): {ref(1)},
    }
    edges_order2 = {
        ref(3): {ref(1)},
        ref(1): {ref(2)},
        ref(2): {ref(3)},
    }
    g1 = graph.Graph(edges_order1)
    g2 = graph.Graph(edges_order2)
    assert g1.cycles() == g2.cycles()
