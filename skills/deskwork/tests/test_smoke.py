import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]


def test_plugin_manifest_is_valid_json():
    manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "deskwork"


def test_skill_file_exists():
    assert (ROOT / "skills" / "deskwork" / "SKILL.md").exists()


def test_skill_dir_is_always_braced():
    """Claude Code substitutes ${CLAUDE_SKILL_DIR} in skill content, and only
    that form. The unbraced form reaches the shell, where the variable is not
    set, so the command runs "/scripts/deskwork.py" and fails."""
    unbraced = "$" + "CLAUDE_SKILL_DIR"
    found = [
        f"{path.relative_to(ROOT)}:{number}"
        for path in sorted((ROOT / "skills").rglob("*"))
        if path.is_file() and path.suffix in {".md", ".sh", ".py"}
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        if unbraced in line
    ]
    assert not found, f"write ${{CLAUDE_SKILL_DIR}} with braces: {found}"
    skill = (ROOT / "skills" / "deskwork" / "SKILL.md").read_text()
    assert "${CLAUDE_SKILL_DIR}/scripts/deskwork.py" in skill
