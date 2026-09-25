"""intake, run as the agent runs it, against a fake GitHub."""
from conftest import deskwork


def test_open_issues_not_on_the_board_are_added_and_read_back(project, github):
    github.issue(1, board_status="Todo")
    github.issue(2)
    github.issue(3)
    github.issue(4, state="CLOSED")
    result = deskwork("intake", cwd=project)
    assert result.returncode == 0, result.stderr
    assert "added 2 issues, read back" in result.stdout
    issues = github.load()["issues"]
    assert issues["owner/repo#2"]["on_board"] and issues["owner/repo#3"]["on_board"]
    assert not issues["owner/repo#4"].get("on_board")


def test_dry_run_lists_and_writes_nothing(project, github):
    github.issue(2)
    result = deskwork("intake", "--dry-run", cwd=project)
    assert result.returncode == 0
    assert "would add #2" in result.stdout
    assert github.writes() == []


def test_without_a_board_there_is_nothing_to_do(project, github):
    config = project / ".github" / "deskwork.toml"
    config.write_text(config.read_text().replace('project = "PVT_kwDOABCD1234"\n', ""))
    result = deskwork("intake", cwd=project)
    assert result.returncode == 0 and "no board configured" in result.stdout
