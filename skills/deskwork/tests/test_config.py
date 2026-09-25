import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import config  # noqa: E402

GOOD = """
enabled = true
project = "PVT_kwDOABCD1234"
triage_status = "Triage"
designs = "docs/superpowers/specs/"
roadmap = "roadmap.md"
issue_types = ["Bug", "Feature", "Task"]
triage_label = "triage"

[labels]
area = ["website", "infra"]
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


def test_the_board_is_optional(tmp_path):
    cfg = config.load(write(tmp_path, GOOD.replace('project = "PVT_kwDOABCD1234"\n', "")))
    assert cfg.project is None
    assert cfg.triage_label == "triage"


def test_the_labels_capture_applies_are_the_labels_init_creates(tmp_path):
    cfg = config.load(write(tmp_path, GOOD))
    assert cfg.labels == ["triage", "area:website", "area:infra"]
    assert cfg.area_label("infra") == "area:infra"


def test_the_old_fields_table_is_refused_with_what_replaced_it(tmp_path):
    root = write(tmp_path, GOOD + '\n[fields]\nStatus = "Triage"\nEffort = ["S"]\n')
    with pytest.raises(config.ConfigError) as caught:
        config.load(root)
    assert "triage_status" in str(caught.value)


@pytest.mark.parametrize("bad", ['issue_types = "Bug"', "issue_types = [1]", 'triage_label = ""'])
def test_malformed_values_are_config_errors(tmp_path, bad):
    key = bad.split(" = ")[0]
    text = "\n".join(line for line in GOOD.splitlines() if not line.startswith(key + " ="))
    with pytest.raises(config.ConfigError):
        config.load(write(tmp_path, text.replace("[labels]", bad + "\n\n[labels]")))


def test_the_starter_is_written_switched_off_and_parses(tmp_path):
    path = config.write_starter(tmp_path)
    assert path == tmp_path / ".github" / "deskwork.toml"
    assert config.load(tmp_path) is None  # enabled = false
    switched_on = path.read_text().replace("enabled = false", "enabled = true")
    path.write_text(switched_on)
    cfg = config.load(tmp_path)
    assert cfg.project is None and cfg.roadmap == "roadmap.md"


def test_the_starter_never_overwrites(tmp_path):
    write(tmp_path, GOOD)
    with pytest.raises(config.ConfigError):
        config.write_starter(tmp_path)


@pytest.mark.parametrize("key", ["roadmap", "designs"])
@pytest.mark.parametrize("value", ["../outside.md", "/tmp/outside.md", "docs/../../outside.md"])
def test_a_path_outside_the_repository_is_a_config_error(tmp_path, key, value):
    text = GOOD.replace(f'{key} = "', f'{key} = "{value}" # was "', 1)
    root = tmp_path / "repo"
    root.mkdir()
    with pytest.raises(config.ConfigError) as caught:
        config.load(write(root, text))
    assert key in str(caught.value) and "inside the repository" in str(caught.value)


def test_a_path_inside_the_repository_is_kept_as_written(tmp_path):
    text = GOOD.replace('roadmap = "roadmap.md"', 'roadmap = "docs/../plans/roadmap.md"')
    assert config.load(write(tmp_path, text)).roadmap == "docs/../plans/roadmap.md"
