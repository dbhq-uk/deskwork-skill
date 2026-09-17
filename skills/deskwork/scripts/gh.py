"""Every call to the gh CLI goes through here, so every call is testable.

Nothing else in deskwork imports subprocess.
"""
import json
import subprocess
import time

_MIN_INTERVAL = 0.2  # five writes a second, to stay clear of secondary rate limits
_last_write = 0.0  # a test can reset this: monkeypatch.setattr(gh, "_last_write", 0.0)


class GhError(Exception):
    """gh exited non-zero. Carries stderr, because its messages are good."""


def _exec(args, stdin_data=None):
    """Build and run the gh command, raising GhError on a non-zero exit.

    The one place that shells out - both run() and api() funnel through
    this, whether or not there is a request body to pipe in on stdin.
    """
    result = subprocess.run(
        ["gh", *args], input=stdin_data, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise GhError(f"gh {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def run(args):
    return _exec(args)


def _pace():
    global _last_write
    wait = _MIN_INTERVAL - (time.monotonic() - _last_write)
    if wait > 0:
        time.sleep(wait)
    _last_write = time.monotonic()


def api(path, method="GET", body=None):
    args = ["api", path]
    if method != "GET":
        _pace()
        args += ["-X", method]
    if body is not None:
        args += ["--input", "-"]
        out = _exec(args, stdin_data=json.dumps(body))
    else:
        out = _exec(args)
    return json.loads(out) if out.strip() else None


def _field_value(value):
    """Render a variable for gh's -F, which type-converts the string it gets.

    -F only recognises lowercase true/false/null - a Python True or None
    would otherwise arrive at GitHub as the literal string "True" or
    "None" and get rejected by a Boolean or nullable field. (-F also
    reads a value starting with "@" from a file rather than passing it
    through - no deskwork caller does that today, but it is a footgun
    for one that does.) Lists and dicts are not supported as GraphQL
    variables through -F - no caller needs them.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def graphql(query, **variables):
    _pace()  # a mutation is a write; graphql() cannot tell it from a query,
    # so every call paces - an extra 0.2s on a read is cheap
    args = ["api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        args += ["-F", f"{key}={_field_value(value)}"]
    return json.loads(run(args))["data"]
