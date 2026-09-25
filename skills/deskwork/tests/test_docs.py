"""SKILL.md and its references say only what the code does."""
import pathlib
import re

import deskwork

SKILL_DIR = pathlib.Path(__file__).resolve().parents[1]
SKILL = (SKILL_DIR / "SKILL.md").read_text()
REFERENCES = sorted((SKILL_DIR / "references").glob("*.md"))


def _links(text):
    return [target for target in re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", text)
            if not target.startswith(("http://", "https://", "mailto:"))]


def test_every_relative_link_in_skill_md_resolves_inside_the_skill():
    links = _links(SKILL)
    assert links, "SKILL.md should point at its references"
    for target in links:
        resolved = (SKILL_DIR / target).resolve()
        assert resolved.is_file(), f"SKILL.md links {target}, which does not exist"
        assert resolved.is_relative_to(SKILL_DIR), f"SKILL.md links {target}, outside the skill"


def test_every_reference_is_linked_from_skill_md():
    linked = {(SKILL_DIR / target).resolve() for target in _links(SKILL)}
    for path in REFERENCES:
        assert path.resolve() in linked, f"{path.name} is not linked from SKILL.md"


def test_no_reference_documents_a_python_function():
    # The agent drives the CLI. A reference that documents issues.create()
    # describes something the agent cannot call.
    for path in REFERENCES:
        text = path.read_text()
        found = re.findall(r"\b[a-z_]+\.[a-z_]+\(|\b[a-z_]+\(\)", text)
        assert not found, f"{path.name} names Python functions: {found}"


def test_skill_md_says_when_not_to_use_it():
    assert "## When not to use" in SKILL


def test_every_mode_skill_md_runs_exists():
    run = re.findall(r'deskwork\.py" (\w+)', SKILL)
    assert run
    for mode in run:
        assert mode in deskwork.MODES, f"SKILL.md runs {mode}, which is not a mode"


def test_every_flag_skill_md_names_exists():
    parser_source = pathlib.Path(deskwork.__file__).read_text()
    flags = set(re.findall(r"(?<![\w-])(--[a-z][a-z-]+)", SKILL))
    assert flags
    for flag in flags:
        assert f'"{flag}"' in parser_source, f"SKILL.md names {flag}, which deskwork.py does not take"


def test_every_exit_code_skill_md_lists_is_one_the_code_returns():
    listed = set(re.findall(r"^\| (\d+) \|", SKILL, re.MULTILINE))
    source = pathlib.Path(deskwork.__file__).read_text()
    returned = set(re.findall(r"return (\d+)\b", source))
    assert listed and listed <= returned, f"SKILL.md lists {listed - returned}, which nothing returns"


def test_agents_md_maps_every_module():
    agents = (SKILL_DIR.parents[1] / "AGENTS.md").read_text()
    for path in sorted((SKILL_DIR / "scripts").glob("*.py")):
        assert f"| `{path.name}` |" in agents, f"AGENTS.md does not map {path.name}"
