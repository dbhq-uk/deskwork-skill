import datetime
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import graph  # noqa: E402
import ids  # noqa: E402
import roadmap  # noqa: E402


def ref(owner, repo, n):
    return ids.Ref(owner, repo, ids.IssueNumber(n))


def build():
    return roadmap.render(
        graph.Graph({ref("owner", "repo", 144): {ref("owner", "repo", 143)}, ref("owner", "repo", 143): set()}),
        titles={ref("owner", "repo", 143): "Register drift", ref("owner", "repo", 144): "Positioning changed"},
        reasons={ref("owner", "repo", 143): "Nothing blocks it, and #144 cannot start until it lands."},
        triage=[ref("owner", "repo", 146)],
        generated=datetime.date(2026, 9, 17),
        issue_count=3,
        home=("owner", "repo"),
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


def test_same_repo_and_cross_repo_in_one_document():
    """Same-repo references render as #N, cross-repo as owner/repo#N."""
    output = roadmap.render(
        graph.Graph({
            ref("owner", "repo", 1): {ref("other", "lib", 99)},
            ref("other", "lib", 99): set(),
        }),
        titles={
            ref("owner", "repo", 1): "First task",
            ref("other", "lib", 99): "External blocker",
        },
        reasons={ref("other", "lib", 99): "Ready to go."},
        triage=[],
        generated=datetime.date(2026, 9, 17),
        issue_count=2,
        home=("owner", "repo"),
    )
    # Cross-repo ready issue uses full format
    assert "1. **other/lib#99**" in output
    # Same-repo blocked issue uses short format
    assert "- **#1**" in output
    # Cross-repo blocker uses full format
    assert "blocked by other/lib#99" in output


def test_output_stability_when_adding_cross_repo_blocker():
    """Adding a cross-repo blocker should not change format of existing lines.

    Regression test: when a cross-repo blocker is added, same-repo references
    must continue to use short format, not switch to full format. This ensures
    adding a single dependency edge does not produce spurious diffs in all lines.
    """
    # First render: all same-repo
    edges1 = {
        ref("owner", "repo", 2): {ref("owner", "repo", 1)},
        ref("owner", "repo", 1): set(),
    }
    output1 = roadmap.render(
        graph.Graph(edges1),
        titles={
            ref("owner", "repo", 1): "First",
            ref("owner", "repo", 2): "Second",
        },
        reasons={ref("owner", "repo", 1): "Nothing blocks it."},
        triage=[],
        generated=datetime.date(2026, 9, 17),
        issue_count=3,
        home=("owner", "repo"),
    )

    # Second render: add a cross-repo blocker for #1
    edges2 = {
        ref("owner", "repo", 2): {ref("owner", "repo", 1)},
        ref("owner", "repo", 1): {ref("other", "lib", 50)},
        ref("other", "lib", 50): set(),
    }
    output2 = roadmap.render(
        graph.Graph(edges2),
        titles={
            ref("owner", "repo", 1): "First",
            ref("owner", "repo", 2): "Second",
            ref("other", "lib", 50): "External blocker",
        },
        reasons={ref("other", "lib", 50): "Ready."},
        triage=[],
        generated=datetime.date(2026, 9, 17),
        issue_count=3,
        home=("owner", "repo"),
    )

    # Verify same-repo references stay in short format in both outputs.
    # The key property: #2 blocks #1, and this line must appear identically in
    # both renders, proving per-reference formatting does not change with document contents.
    assert "- **#2** Second - blocked by #1" in output1
    assert "- **#2** Second - blocked by #1" in output2
