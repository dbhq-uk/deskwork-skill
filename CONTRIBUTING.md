# Contributing

Thanks for your interest - contributions are welcome.

## Ways to help

- Report a bug or request a feature via [issues](https://github.com/dbhq-uk/deskwork-skill/issues)
- Sharpen the skill's instructions or improve an error message via a pull request

## Local development

```bash
git clone https://github.com/dbhq-uk/deskwork-skill.git
cd deskwork-skill
python3 -m pytest skills/deskwork/tests -q
```

## Before opening a PR

```bash
jq empty .claude-plugin/plugin.json                  # the manifest is valid JSON
python3 -m pytest skills/deskwork/tests -q            # the tests pass
```

CI runs those, plus two checks on the prose: no em dashes, and nothing that
looks like a real ticket id. British English, plain hyphens, no trailing full
stops on headings.

## What we will not accept

**Anything that needs a package.** deskwork is Python standard library only.
There is no `requirements.txt` and no venv, which is why there is nothing to
keep patched.

**A real ticket id, hostname, IP address or organisation.** CI greps the
markdown for the ticket-id shape, and review catches the rest. Every example in
the docs is generic (`owner/repo`, `#123`) and should stay that way.

## Code of conduct

By taking part you agree to the [code of conduct](CODE_OF_CONDUCT.md).

## Licence

By contributing you agree your work is licensed under the [MIT licence](LICENSE).
