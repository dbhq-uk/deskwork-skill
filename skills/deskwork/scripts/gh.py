"""Every call to the gh CLI goes through here, so every call is testable.

Nothing else in deskwork imports subprocess.
"""
import json
import subprocess
import time

_MIN_INTERVAL = 0.2  # five writes a second, to stay clear of secondary rate limits
_last_write = 0.0


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


def graphql(query, **variables):
    args = ["api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        args += ["-F", f"{key}={value}"]
    return json.loads(run(args))["data"]
