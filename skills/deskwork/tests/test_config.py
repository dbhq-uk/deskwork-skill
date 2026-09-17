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


@pytest.mark.parametrize(
    "enabled_value",
    [
        'enabled = "true"',
        "enabled = 1",
        'enabled = "yes"',
        "enabled = [true]",
        "enabled = 1.0",
        'enabled = "True"',
    ],
)
def test_only_literal_true_opens_gate(tmp_path, enabled_value):
    root = write(tmp_path, GOOD.replace("enabled = true", enabled_value))
    assert config.load(root) is None


def test_malformed_toml_raises_config_error(tmp_path):
    root = write(tmp_path, "enabled = true\nthis is not valid toml [[[")
    with pytest.raises(config.ConfigError) as caught:
        config.load(root)
    assert "not valid TOML" in str(caught.value)


def test_directory_in_place_of_file_raises_config_error(tmp_path):
    (tmp_path / ".github").mkdir(exist_ok=True)
    (tmp_path / ".github" / "deskwork.toml").mkdir(exist_ok=True)
    with pytest.raises(config.ConfigError) as caught:
        config.load(tmp_path)
    assert "cannot be read" in str(caught.value)


def test_symlink_outside_repo_root_means_no_config(tmp_path):
    other_repo = tmp_path / "other"
    other_repo.mkdir()
    (other_repo / ".github").mkdir(exist_ok=True)
    (other_repo / ".github" / "deskwork.toml").write_text(GOOD)

    repo = tmp_path / "this"
    repo.mkdir()
    (repo / ".github").mkdir(exist_ok=True)
    link = repo / ".github" / "deskwork.toml"
    link.symlink_to(other_repo / ".github" / "deskwork.toml")

    assert config.load(repo) is None
