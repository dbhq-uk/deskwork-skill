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
