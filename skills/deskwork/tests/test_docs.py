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


# The descriptions of headwork and life-manager, copied from
# dbhq-uk/headwork-skill and dbhq-uk/trello-skill. Both answer to "what should
# I do next" in some form, so no deskwork trigger may appear anywhere in either.
NEIGHBOUR_DESCRIPTIONS = {
    "headwork": (
        "Think a decision through, one question at a time, with a recommendation you "
        "can argue with. When the user is stuck between options on the work in hand, "
        "headwork explains the decision, asks one question with a justification on "
        "every option, names the recommendation and says what would overturn it. It "
        "never asks what it could have looked up. Use when the user says \"headwork\", "
        "\"I'm stuck between\", \"stuck on which\", \"how do I move this forward\", \"unblock "
        "me\", \"unblock this\", \"which way\", \"help me decide\", \"I can't decide\", \"what "
        "should I do here\", or \"talk me through the options\". Not for designing "
        "something new, stress-testing a whole plan, or picking the next issue."
    ),
    "life-manager": (
        "Set up and run a Trello board that actually gets things done - capture ideas, "
        "triage them into a working queue, and coach the user through what has stalled. "
        "Three modes - setup, triage, coach. Trigger on phrases like \"set up my life "
        "board\", \"help me get stuff done\", \"sort my inbox\", \"what should I do next\", "
        "\"I'm stuck\", \"nothing is moving\", \"life manager\", \"manage my todo board\"."
    ),
}

# Phrases another skill answers to, or that ask about some other queue. A
# deskwork trigger that contains one of these, or sits inside one, fires
# deskwork for a request that belongs elsewhere.
OTHER_PHRASES = {
    "any other queue, an email queue for example": ["what's queued", "what's waiting"],
    "headwork, before its triggers narrowed": ["what's next"],
    "life-manager, in the plural": ["what should we do next"],
    "buildwork": ["run the roadmap", "work through the backlog", "what's running",
                  "which order do I merge these"],
    "atlassian": ["raise a jira ticket", "create a jira ticket", "jira"],
    "pennyblack": ["track that letter", "post this letter", "put this in the post"],
}


def _frontmatter_description():
    match = re.search(r"^description: (.*)$", SKILL, re.MULTILINE)
    assert match, "SKILL.md has no one-line description"
    return match.group(1)


def _triggers():
    triggers = _quoted(_frontmatter_description())
    assert triggers, "the description names no trigger phrases"
    return triggers


def _quoted(text):
    return re.findall(r'"([^"]+)"', text)


def test_the_broad_phrases_are_gone():
    root = SKILL_DIR.parents[1]
    for name in ("SKILL.md", "README.md", "install.sh", "install-codex.sh"):
        path = SKILL_DIR / name if name == "SKILL.md" else root / name
        text = path.read_text().lower()
        for phrase in ("what's queued", "what should we do next"):
            assert phrase not in text, f"{name} still says {phrase!r}"


def test_no_trigger_phrase_appears_in_a_neighbouring_description():
    for trigger in _triggers():
        for owner, description in NEIGHBOUR_DESCRIPTIONS.items():
            assert trigger.lower() not in description.lower(), f'"{trigger}" is in {owner}\'s description'


def test_no_trigger_phrase_overlaps_one_another_skill_answers_to():
    others = {**OTHER_PHRASES, **{owner: _quoted(text) for owner, text in NEIGHBOUR_DESCRIPTIONS.items()}}
    for trigger in _triggers():
        for owner, phrases in others.items():
            for phrase in phrases:
                a, b = trigger.lower(), phrase.lower()
                assert a not in b and b not in a, f'"{trigger}" overlaps "{phrase}" ({owner})'


def test_the_description_is_a_plain_yaml_scalar_that_survives_parsing():
    # Unquoted, ": " makes the frontmatter invalid YAML and " #" starts a
    # comment, which silently cuts the description short.
    description = _frontmatter_description()
    assert ": " not in description
    assert " #" not in description


def test_install_suggests_only_phrases_the_skill_triggers_on():
    install = (SKILL_DIR.parents[1] / "install.sh").read_text()
    line = re.search(r"Then try: (.*)", install)
    assert line, "install.sh no longer suggests anything to try"
    suggested = re.findall(r"'(.*?)'(?=,|\s+or\s|\"?$)", line.group(1))
    assert suggested
    for phrase in suggested:
        assert phrase in _triggers(), f"install.sh suggests '{phrase}', which is not a trigger"
