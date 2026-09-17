import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]


def test_plugin_manifest_is_valid_json():
    manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "deskwork"


def test_skill_file_exists():
    assert (ROOT / "skills" / "deskwork" / "SKILL.md").exists()
