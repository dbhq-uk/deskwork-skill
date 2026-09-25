"""Read .github/deskwork.toml, or refuse to do anything.

No file, or enabled missing or false, means deskwork writes nothing. Not a
warning, not a prompt. A repository that has not asked for this cannot be
written to by an accident in somebody's session.
"""
import tomllib
from dataclasses import dataclass, field

CONFIG_PATH = ".github/deskwork.toml"


class ConfigError(Exception):
    """The file exists and is wrong. Distinct from the file not existing."""


@dataclass
class Config:
    project: str
    designs: str
    roadmap: str
    issue_types: list
    area_labels: list
    triage_status: str
    triage_label: str = "triage"
    effort: list = field(default_factory=list)
    risk: list = field(default_factory=list)


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

    project = data.get("project", "")
    if not project.startswith("PVT_"):
        raise ConfigError(
            f"{CONFIG_PATH}: project must be a Projects v2 node id starting PVT_, "
            f"not a title. Got {project!r}. Projects v2 titles are not unique and "
            "--add-project silently picks the wrong board. Find the id with: "
            "gh project list --owner OWNER --format json"
        )

    for key in ("designs", "roadmap"):
        if not data.get(key):
            raise ConfigError(f"{CONFIG_PATH}: {key} is required")

    fields = data.get("fields", {})
    return Config(
        project=project,
        designs=data["designs"],
        roadmap=data["roadmap"],
        issue_types=data.get("issue_types", []),
        area_labels=data.get("labels", {}).get("area", []),
        triage_status=fields.get("Status", "Triage"),
        triage_label=data.get("triage_label", "triage"),
        effort=fields.get("Effort", []),
        risk=fields.get("Risk", []),
    )
