"""roadmap, run as the agent runs it, against a fake GitHub and a real git repo."""
import json
import re

from conftest import deskwork, git


def _sections(text):
    """{heading: [issue refs listed under it]}, first reference per list item."""
    found, current = {}, None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:]
            found[current] = []
        elif current and re.match(r"^\s*(?:[-*]|\d+[.)])\s+", line):
            ref = re.search(r"(?:[\w.-]+/[\w.-]+)?#\d+", line)
            if ref:
                found[current].append(ref.group(0))
    return found


def _buildwork_runnable(text):
    """What buildwork would run, by its own rules (buildwork-skill
    skills/buildwork/scripts/roadmap.py): list items under a heading that
    starts next/now/in progress/ready, first reference only, local only."""
    runnable, section_runs, seen = [], False, set()
    for line in text.splitlines():
        if line.startswith("## "):
            name = line[3:].strip().lower()
            section_runs = name.startswith(("next", "now", "in progress", "ready"))
            continue
        item = re.match(r"^\s*(?:[-*]|\d+[.)])\s+(.*)$", line)
        if not item:
            continue
        ref = re.search(r"(?P<repo>[\w.-]+/[\w.-]+)?#(?P<num>\d+)", item.group(1))
        if not ref or ref.group("repo") or int(ref.group("num")) in seen:
            continue
        seen.add(int(ref.group("num")))
        if section_runs:
            runnable.append(int(ref.group("num")))
    return runnable


def _board(github):
    github.issue(5, "Old blocker", state="CLOSED")
    github.issue(6, "Was blocked by a closed issue", blocked_by=[5])
    github.issue(7, "Schema")
    github.issue(8, "Migration", blocked_by=[7])
    github.issue(11, "Filed by an agent", labels=["triage"])
    github.issue(12, "Filed and blocked", labels=["triage"], blocked_by=[7])
    github.issue(13, "On the board in Triage", board_status="Triage")


def test_a_closed_blocker_and_triage_issues_stay_out_of_next_and_blocked(project, github):
    _board(github)
    result = deskwork("roadmap", "--dry-run", cwd=project)
    assert result.returncode == 0, result.stderr
    sections = _sections(result.stdout)
    assert sections["Next"] == []
    assert sections["Blocked"] == ["#8"]
    assert sections["Later"] == ["#6", "#7"]  # #6 is ready: its only blocker closed
    assert sections["Triage"] == ["#11", "#12", "#13"]
    everywhere = [ref for refs in sections.values() for ref in refs]
    assert "#5" not in everywhere
    assert _buildwork_runnable(result.stdout) == []


def test_the_order_is_kept_with_a_reason_under_each_item(project, github, tmp_path):
    _board(github)
    order = tmp_path / "order.json"
    order.write_text(json.dumps([
        {"ref": "#7", "reason": "Unblocks the migration."},
        {"ref": "#6", "reason": "Free now its blocker closed."},
    ]))
    result = deskwork("roadmap", "--dry-run", "--order", str(order), cwd=project)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    first = lines.index("1. **#7** Schema")
    assert lines[first + 1] == "   Why: Unblocks the migration."
    second = lines.index("2. **#6** Was blocked by a closed issue")
    assert lines[second + 1] == "   Why: Free now its blocker closed."
    assert "## Later" not in result.stdout  # everything ready was ordered
    assert _buildwork_runnable(result.stdout) == [7, 6]


def test_the_order_can_come_from_stdin(project, github):
    _board(github)
    result = deskwork("roadmap", "--dry-run", "--order", "-", cwd=project,
                      stdin='[{"ref": 7, "reason": "First."}]')
    assert result.returncode == 0, result.stderr
    assert "1. **#7** Schema" in result.stdout


def _refused(project, github, tmp_path, ref, expected):
    _board(github)
    order = tmp_path / "order.json"
    order.write_text(json.dumps([{"ref": "#7", "reason": "fine"}, {"ref": ref, "reason": "why not"}]))
    result = deskwork("roadmap", "--order", str(order), cwd=project)
    assert result.returncode == 1
    assert expected in result.stderr
    assert not (project / "roadmap.md").exists()
    assert git(project, "log", "--oneline").count("\n") == 1


def test_a_closed_issue_in_the_order_is_refused_by_name(project, github, tmp_path):
    github.issue(5, state="CLOSED")
    _refused(project, github, tmp_path, "#5", "#5 is closed.")


def test_a_triage_issue_in_the_order_is_refused_by_name(project, github, tmp_path):
    _refused(project, github, tmp_path, "#11", "#11 is still in Triage.")


def test_an_issue_in_triage_on_the_board_is_refused_by_name(project, github, tmp_path):
    _refused(project, github, tmp_path, "#13", "#13 is still in Triage.")


def test_a_blocked_issue_in_the_order_is_refused_by_name(project, github, tmp_path):
    _refused(project, github, tmp_path, "#8", "#8 is blocked by #7, which is still open.")


def test_an_entry_without_a_reason_is_refused(project, github, tmp_path):
    _board(github)
    order = tmp_path / "order.json"
    order.write_text('[{"ref": "#7"}]')
    result = deskwork("roadmap", "--order", str(order), cwd=project)
    assert result.returncode == 1
    assert "#7 has no reason" in result.stderr


def test_writing_needs_an_order(project, github):
    _board(github)
    result = deskwork("roadmap", cwd=project)
    assert result.returncode == 1
    assert "--order is required" in result.stderr


def test_a_successful_run_commits_the_roadmap_file_alone(project, github, tmp_path):
    _board(github)
    # Other work in progress must not ride along in the roadmap commit.
    (project / "staged.txt").write_text("staged\n")
    git(project, "add", "staged.txt")
    (project / "unstaged.txt").write_text("unstaged\n")
    order = tmp_path / "order.json"
    order.write_text(json.dumps([{"ref": "#7", "reason": "Unblocks the migration."}]))

    result = deskwork("roadmap", "--order", str(order), cwd=project)
    assert result.returncode == 0, result.stderr
    assert "committed it alone" in result.stdout
    stat = git(project, "log", "-1", "--stat", "--format=%s")
    assert stat.splitlines()[0] == "docs(roadmap): refresh from 6 open issues"
    assert git(project, "log", "-1", "--name-only", "--format=").split() == ["roadmap.md"]
    assert "A  staged.txt" in git(project, "status", "--porcelain")

    again = deskwork("roadmap", "--order", str(order), cwd=project)
    assert again.returncode == 0 and "unchanged" in again.stdout


def test_run_from_a_worktree_subdirectory_it_commits_at_the_worktree_root(project, github, tmp_path):
    _board(github)
    worktree = tmp_path / "wt"
    git(project, "worktree", "add", "-q", str(worktree), "-b", "side")
    (worktree / "src").mkdir()
    order = tmp_path / "order.json"
    order.write_text(json.dumps([{"ref": "#7", "reason": "First."}]))
    result = deskwork("roadmap", "--order", str(order), cwd=worktree / "src")
    assert result.returncode == 0, result.stderr
    assert (worktree / "roadmap.md").exists()
    assert git(worktree, "log", "-1", "--name-only", "--format=").split() == ["roadmap.md"]


def test_roadmap_never_writes_outside_the_repository(project, github, tmp_path):
    _board(github)
    toml = project / ".github" / "deskwork.toml"
    toml.write_text(toml.read_text().replace('roadmap = "roadmap.md"', 'roadmap = "../outside.md"'))
    order = tmp_path / "order.json"
    order.write_text(json.dumps([{"ref": "#7", "reason": "Unblocks the migration."}]))
    result = deskwork("roadmap", "--order", str(order), cwd=project)
    assert result.returncode == 3, result.stderr
    assert "inside the repository" in result.stderr
    assert not (project.parent / "outside.md").exists()
