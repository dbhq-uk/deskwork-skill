"""The repository's own documents describe the skill that ships."""
import pathlib
import re

SKILL_DIR = pathlib.Path(__file__).resolve().parents[1]
ROOT = SKILL_DIR.parents[1]
SCRIPTS = sorted((SKILL_DIR / "scripts").glob("*.py"))
SKIP = {".git", "__pycache__", ".pytest_cache", ".local"}


def _text_files():
    for path in ROOT.rglob("*"):
        if path.is_file() and not SKIP & set(path.relative_to(ROOT).parts):
            try:
                yield path, path.read_text()
            except UnicodeDecodeError:
                continue


def _prose(name):
    return " ".join((ROOT / name).read_text().split())


def test_no_stray_scratch_script_ships_with_the_skill():
    stray = [p.relative_to(ROOT).as_posix() for p in SKILL_DIR.rglob("tmp*.py")]
    assert not stray, f"scratch files would be installed with the skill: {stray}"


def test_the_repository_is_named_deskwork_skill_everywhere():
    # The old name works only through GitHub's rename redirect. Built in two
    # halves so this file does not match its own pattern.
    old = re.compile("dbhq-uk/" + r"deskwork(?!-skill)\b")
    for path, text in _text_files():
        assert not old.search(text), f"{path.relative_to(ROOT)} uses the old repository name, not deskwork-skill"


def test_every_relative_link_in_the_top_level_docs_resolves_inside_the_repository():
    for name in ("README.md", "AGENTS.md", "CONTRIBUTING.md", "SECURITY.md"):
        text = (ROOT / name).read_text()
        for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (ROOT / target).resolve()
            assert resolved.is_relative_to(ROOT), f"{name} links {target}, outside the repository"
            assert resolved.exists(), f"{name} links {target}, which does not exist"


def test_every_path_in_the_agents_md_layout_exists():
    block = re.search(r"## Layout\s+```\n(.*?)```", (ROOT / "AGENTS.md").read_text(), re.S)
    assert block, "AGENTS.md has no layout block"
    for line in block.group(1).splitlines():
        entry = line.split("#", 1)[0].strip()
        for path in filter(None, (part.strip() for part in entry.split(" / "))):
            assert (ROOT / path).exists(), f"AGENTS.md lists {path}, which does not exist"


def test_no_script_touches_a_pull_request():
    # README, AGENTS.md and SECURITY.md say deskwork never touches a pull
    # request. That holds only while no script calls gh pr or the pulls API.
    for path in SCRIPTS:
        text = path.read_text()
        assert not re.search(r'\[\s*"pr"\s*,', text), f"{path.name} calls gh pr"
        assert "/pulls" not in text, f"{path.name} calls the pulls API"


def test_what_the_docs_say_ci_greps_for_is_what_ci_greps_for():
    validate = (ROOT / ".github/workflows/validate.yml").read_text()
    assert "[A-Z]{3,}-[0-9]{3,}" in validate
    for name in ("AGENTS.md", "CONTRIBUTING.md"):
        for claim in re.findall(r"CI greps[^.]*\.", _prose(name)):
            for thing in ("hostname", "IP address", "organisation"):
                assert thing not in claim, f"{name} says CI greps for {thing}; it does not: {claim}"


# Claims that were once in these documents and were never true of the code.
RETIRED = {
    "README.md": [
        "may propose a merge order",
        "scope is not granted",
        "docs/superpowers",
    ],
    "AGENTS.md": [
        "`capture` may add `Closes #N`",
        "docs/superpowers",
    ],
    "SECURITY.md": [
        "scaffold",
        "stub",
        "not yet implemented",
    ],
}


def test_retired_claims_stay_retired():
    for name, claims in RETIRED.items():
        text = _prose(name)
        for claim in claims:
            assert claim not in text, f"{name} says {claim!r} again"


def test_security_md_names_every_mode_that_writes():
    security = (ROOT / "SECURITY.md").read_text()
    for mode in ("capture", "init", "link", "unlink", "roadmap"):
        assert f"`{mode}`" in security, f"SECURITY.md does not say what {mode} writes"
