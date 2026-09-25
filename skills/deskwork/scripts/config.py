"""Read .github/deskwork.toml, or refuse to do anything.

No file, or enabled missing or false, means deskwork writes nothing. Not a
warning, not a prompt. A repository that has not asked for this cannot be
written to by an accident in somebody's session. The one exception is init
in a repository with no file at all: it writes the starter, with enabled =
false, and stops.
"""
import pathlib
import tomllib
from dataclasses import dataclass, field

CONFIG_PATH = ".github/deskwork.toml"
STARTER = pathlib.Path(__file__).resolve().parent.parent / "deskwork.toml.example"


class ConfigError(Exception):
    """The file exists and is wrong. Distinct from the file not existing."""


@dataclass
class Config:
    designs: str
    roadmap: str
    issue_types: list = field(default_factory=list)
    area_labels: list = field(default_factory=list)
    triage_label: str = "triage"
    project: str = None  # a Projects v2 node id, or None for no board
    triage_status: str = "Triage"

    def area_label(self, area):
        """The label capture applies and init creates for an area."""
        return f"area:{area}"

    @property
    def labels(self):
        """Every label deskwork applies, in the order init creates them."""
        return [self.triage_label] + [self.area_label(a) for a in self.area_labels]


def exists(repo_root):
    return (repo_root / CONFIG_PATH).exists()


def write_starter(repo_root):
    """Write the starter config, disabled. Never overwrites an existing file."""
    path = repo_root / CONFIG_PATH
    if path.exists():
        raise ConfigError(f"{CONFIG_PATH} already exists")
    text = STARTER.read_text()
    if "\nenabled = false\n" not in f"\n{text}":
        raise ConfigError("the starter config must ship with enabled = false")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _strings(data, key, where=CONFIG_PATH):
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise ConfigError(f"{where}: {key} must be a list of names")
    return value


def load(repo_root):
    path = repo_root / CONFIG_PATH
    if not path.exists():
        return None
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return None
    if not resolved.is_relative_to(repo_root.resolve()):
        return None
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{CONFIG_PATH}: not valid TOML ({error})") from error
    except OSError as error:
        raise ConfigError(f"{CONFIG_PATH}: cannot be read ({error})") from error
    if data.get("enabled") is not True:
        return None

    if "fields" in data:
        raise ConfigError(
            f"{CONFIG_PATH}: [fields] is no longer read. Effort and Risk are GitHub "
            "issue fields now, not board fields deskwork creates. The board's Triage "
            'option is triage_status = "Triage", next to project.'
        )

    project = data.get("project")
    if project is not None and not (isinstance(project, str) and project.startswith("PVT_")):
        raise ConfigError(
            f"{CONFIG_PATH}: project must be a Projects v2 node id starting PVT_, "
            f"not a title. Got {project!r}. Projects v2 titles are not unique and "
            "--add-project silently picks the wrong board. Find the id with: "
            "gh project list --owner OWNER --format json. Or leave project out "
            "to work from labels alone."
        )

    for key in ("designs", "roadmap"):
        if not data.get(key):
            raise ConfigError(f"{CONFIG_PATH}: {key} is required")
        # roadmap writes to this path. Checked here, before any mode runs,
        # because a value like "../roadmap.md" or "/tmp/roadmap.md" would
        # otherwise be written first and found wrong afterwards.
        value = data[key]
        if (not isinstance(value, str) or pathlib.PurePath(value).is_absolute()
                or not (repo_root / value).resolve().is_relative_to(repo_root.resolve())):
            raise ConfigError(
                f"{CONFIG_PATH}: {key} must be a path inside the repository, "
                f"relative to its root. Got {value!r}."
            )

    triage_label = data.get("triage_label", "triage")
    if not isinstance(triage_label, str) or not triage_label.strip():
        raise ConfigError(f"{CONFIG_PATH}: triage_label must be a label name")

    labels = data.get("labels", {})
    if not isinstance(labels, dict):
        raise ConfigError(f"{CONFIG_PATH}: [labels] must be a table")

    return Config(
        designs=data["designs"],
        roadmap=data["roadmap"],
        issue_types=_strings(data, "issue_types"),
        area_labels=_strings(labels, "area", f"{CONFIG_PATH} [labels]"),
        triage_label=triage_label,
        project=project,
        triage_status=data.get("triage_status", "Triage"),
    )
