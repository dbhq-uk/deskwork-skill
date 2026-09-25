"""Every call to the gh CLI goes through here, so every call is testable.

Nothing else in deskwork runs gh, and only git.py runs git. That is what lets
this module refuse, before gh is ever started, any call that would close,
delete or transfer an issue (AGENTS.md constraint 1). The refusal is here
rather than in each caller because a grep for the obvious spellings misses the
rest: a GraphQL mutation, an argv list, a PATCH body, a flag in extra_args.
"""
import json
import re
import subprocess
import time

MIN_VERSION = (2, 94, 0)  # gh issue create --type/--parent/--blocked-by, edit --add-blocked-by
UPGRADE = "https://github.com/cli/cli#installation"

_MIN_INTERVAL = 0.2  # five writes a second, to stay clear of secondary rate limits
_last_write = 0.0  # a test can reset this: monkeypatch.setattr(gh, "_last_write", 0.0)


class GhError(Exception):
    """gh exited non-zero. Carries stderr, because its messages are good."""


class Refused(Exception):
    """A call that would close, delete or transfer an issue. Never sent."""


class TooOld(Exception):
    """The gh on PATH predates the flags deskwork is built on."""


_ISSUE_VERBS = {"close", "delete", "transfer"}
_MUTATIONS = re.compile(r"\b(closeIssue|deleteIssue|transferIssue|updateIssue)\b")
_ISSUE_PATH = re.compile(r"^/?repos/[^/]+/[^/]+/issues/\d+/?$")
_STATE_KEYS = {"state", "state_reason"}


def _refuse(what):
    raise Refused(
        f"deskwork never closes, deletes or transfers an issue, and refused: {what}"
    )


def _api_method(args):
    """The HTTP method a gh api argv asks for, however it is spelled."""
    method = "GET"
    for index, arg in enumerate(args):
        if arg in ("-X", "--method") and index + 1 < len(args):
            method = args[index + 1]
        elif arg.startswith("--method="):
            method = arg.split("=", 1)[1]
        elif arg.startswith("-X") and len(arg) > 2:
            method = arg[2:]
    return method.upper()


def _api_fields(args):
    """The key=value fields a gh api argv sends, from -f, -F and their long forms."""
    fields = {}
    for index, arg in enumerate(args):
        value = None
        if arg in ("-f", "-F", "--field", "--raw-field") and index + 1 < len(args):
            value = args[index + 1]
        elif arg.startswith(("--field=", "--raw-field=")):
            value = arg.split("=", 1)[1]
        if value is not None and "=" in value:
            key, _, rest = value.partition("=")
            fields[key] = rest
    return fields


_VALUE_FLAGS = {
    "-X", "--method", "-f", "-F", "--field", "--raw-field", "-H", "--header",
    "--input", "-q", "--jq", "-t", "--template", "--hostname", "--cache", "-p", "--preview",
}


def _api_path(args):
    """The endpoint of a gh api argv: its first positional, wherever it sits."""
    skip = False
    for arg in args[1:]:
        if skip:
            skip = False
            continue
        if arg in _VALUE_FLAGS:
            skip = True
            continue
        if arg.startswith("-"):
            continue
        return arg
    return ""


def _graphql_text(args, stdin_data):
    """The query and variables of a gh api graphql call, as one string to search."""
    parts = [value for key, value in _api_fields(args).items() if key == "query"]
    if stdin_data:
        parts.append(stdin_data)
    return "\n".join(parts)


def _guard(args, stdin_data):
    if len(args) >= 2 and args[0] == "issue" and args[1] in _ISSUE_VERBS:
        _refuse(f"gh issue {args[1]}")
    if not args or args[0] != "api":
        return
    method = _api_method(args)
    path = _api_path(args)
    if method == "DELETE":
        # Nothing deskwork does needs DELETE. Edges come off through
        # gh issue edit --remove-blocked-by.
        _refuse(f"DELETE {path}")
    if path == "graphql":
        if _MUTATIONS.search(_graphql_text(args, stdin_data)):
            _refuse("a closeIssue, deleteIssue, transferIssue or updateIssue mutation")
        return
    if method in ("PATCH", "POST", "PUT") and _ISSUE_PATH.match(path):
        keys = set(_api_fields(args))
        if stdin_data:
            try:
                body = json.loads(stdin_data)
            except ValueError:
                body = {}
            if isinstance(body, dict):
                keys |= set(body)
        if keys & _STATE_KEYS:
            _refuse(f"{method} {path} carrying {sorted(keys & _STATE_KEYS)}")


def _exec(args, stdin_data=None, cwd=None):
    """Build and run the gh command, raising GhError on a non-zero exit.

    The one place that shells out. The guard runs first, so a refused call
    never reaches gh at all.
    """
    _guard(args, stdin_data)
    result = subprocess.run(
        ["gh", *args], input=stdin_data, capture_output=True, text=True, cwd=cwd
    )
    if result.returncode != 0:
        raise GhError(f"gh {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def _pace():
    global _last_write
    wait = _MIN_INTERVAL - (time.monotonic() - _last_write)
    if wait > 0:
        time.sleep(wait)
    _last_write = time.monotonic()


def run(args, stdin_data=None, cwd=None, write=False):
    """Run any gh command. Pass write=True for one that changes GitHub."""
    if write:
        _pace()
    return _exec(args, stdin_data=stdin_data, cwd=cwd)


def run_json(args, stdin_data=None, cwd=None, write=False):
    out = run(args, stdin_data=stdin_data, cwd=cwd, write=write)
    return json.loads(out) if out.strip() else None


def api(path, method="GET", body=None, extra_args=None):
    args = ["api", path]
    if method != "GET":
        _pace()
        args += ["-X", method]
    if extra_args:
        args.extend(extra_args)
    if body is not None:
        args += ["--input", "-"]
        out = _exec(args, stdin_data=json.dumps(body))
    else:
        out = _exec(args)
    return json.loads(out) if out.strip() else None


def graphql(query, **variables):
    """Send a query with its variables as one JSON body.

    The body goes through --input rather than -F, so a list or an object
    arrives at GitHub as a list or an object. -F renders every value as a
    string, which is how a field's options once arrived as a Python repr.
    """
    if query.lstrip().startswith("mutation"):
        _pace()
    payload = json.dumps({"query": query, "variables": variables})
    return json.loads(_exec(["api", "graphql", "--input", "-"], stdin_data=payload))["data"]


def version():
    """The installed gh version as a tuple, e.g. (2, 100, 0)."""
    out = _exec(["--version"])
    match = re.search(r"gh version (\d+)\.(\d+)\.(\d+)", out)
    if not match:
        raise GhError(f"cannot read the gh version from: {out.strip()!r}")
    return tuple(int(part) for part in match.groups())


def require_version(minimum=MIN_VERSION):
    found = version()
    if found < minimum:
        raise TooOld(
            f"deskwork needs gh {'.'.join(map(str, minimum))} or later, and this is "
            f"gh {'.'.join(map(str, found))}. Upgrade gh: {UPGRADE}"
        )
    return found
