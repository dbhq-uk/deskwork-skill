import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import config  # noqa: E402

GOOD = """
enabled = true
project = "PVT_kwDOABCD1234"
designs = "docs/superpowers/specs/"
roadmap = "roadmap.md"
issue_types = ["Bug", "Feature", "Task"]

[labels]
area = ["website", "infra"]

[fields]
Status = "Triage"
Effort = ["S", "M", "L", "XL"]
Risk = ["low", "medium", "high"]
"""


def write(tmp_path, text):
    (tmp_path / ".github").mkdir(exist_ok=True)
    (tmp_path / ".github" / "deskwork.toml").write_text(text)
    return tmp_path


def test_no_file_means_no_config(tmp_path):
    assert config.load(tmp_path) is None


def test_enabled_false_means_no_config(tmp_path):
    root = write(tmp_path, GOOD.replace("enabled = true", "enabled = false"))
    assert config.load(root) is None


def test_missing_enabled_key_means_no_config(tmp_path):
    root = write(tmp_path, GOOD.replace("enabled = true\n", ""))
    assert config.load(root) is None


def test_a_good_file_loads(tmp_path):
    cfg = config.load(write(tmp_path, GOOD))
    assert cfg.project == "PVT_kwDOABCD1234"
    assert cfg.triage_status == "Triage"
    assert "website" in cfg.area_labels


def test_a_project_title_is_rejected(tmp_path):
    root = write(tmp_path, GOOD.replace('"PVT_kwDOABCD1234"', '"DBHQ Board"'))
    with pytest.raises(config.ConfigError) as caught:
        config.load(root)
    assert "node id" in str(caught.value).lower()
