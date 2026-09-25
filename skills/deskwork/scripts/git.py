"""Every call to git goes through here, as every call to gh goes through gh.py."""
import subprocess


class GitError(Exception):
    """git exited non-zero. Carries stderr."""


def run(args, cwd):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout
