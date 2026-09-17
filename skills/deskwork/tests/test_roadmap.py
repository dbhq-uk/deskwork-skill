import datetime
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import graph  # noqa: E402
import ids  # noqa: E402
import roadmap  # noqa: E402


def ref(n):
    return ids.Ref("owner", "repo", ids.IssueNumber(n))


def build():
    return roadmap.render(
        graph.Graph({ref(144): {ref(143)}, ref(143): set()}),
        titles={ref(143): "Register drift", ref(144): "Positioning changed"},
        reasons={ref(143): "Nothing blocks it, and #144 cannot start until it lands."},
        triage=[ref(146)],
        generated=datetime.date(2026, 9, 17),
        issue_count=3,
    )


def test_it_states_when_and_from_what():
    assert "2026-09-17" in build()
    assert "3 open issues" in build()


def test_it_says_the_order_is_reasoned_not_computed():
    assert "reasoned" in build().lower()


def test_a_blocked_item_shows_its_blocker():
    assert "blocked by #143" in build()


def test_triage_is_listed_but_not_ordered():
    text = build()
    assert "#146" in text
    assert text.index("## Triage") > text.index("## Next")


def test_no_em_dashes():
    # Escapes, not the literal characters: CI greps every file for them,
    # including this one, so a literal here fails the build it protects.
    assert "—" not in build() and "–" not in build()
