#!/usr/bin/env python3
"""deskwork - file what an agent notices, order it, and keep a roadmap in git.

This script never closes an issue, never deletes one, and never writes to any
repository without .github/deskwork.toml carrying enabled = true.
"""
import argparse
import datetime
import json
import pathlib
import sys

import board
import config
import deps
import gh
import graph
import ids
import issues
import memory
import roadmap

MODES = ("capture", "review", "roadmap", "init", "intake", "doctor")


def _get_owner_repo(repo_path):
    """Extract owner/repo from git remote origin.

    Returns (owner, repo) tuple, raises ValueError if not a git repo or
    cannot determine remote.
    """
    git_dir = repo_path / ".git"
    if not git_dir.exists():
        raise ValueError(f"{repo_path} is not a git repository")

    config_path = git_dir / "config"
    if not config_path.exists():
        raise ValueError(f"cannot read git config at {config_path}")

    content = config_path.read_text()
    for line in content.split("\n"):
        if "url =" in line and "github.com" in line:
            url = line.split("=", 1)[1].strip()
            # Parse git@github.com:owner/repo.git or https://github.com/owner/repo.git
            if "github.com" in url:
                if url.endswith(".git"):
                    url = url[:-4]
                if ":" in url:
                    # ssh format
                    url = url.split(":", 1)[1]
                # Extract owner/repo
                parts = url.split("/")
                if len(parts) >= 2:
                    return (parts[-2], parts[-1])
    raise ValueError(f"cannot determine GitHub owner/repo from {repo_path}")


def mode_capture(args, cfg):
    """File a new issue: duplicate search, create, add to board, set to Triage."""
    if not args.title:
        sys.stderr.write("capture: --title is required\n")
        return 1

    try:
        owner, repo = _get_owner_repo(args.repo)
    except ValueError as e:
        sys.stderr.write(f"capture: {e}\n")
        return 1

    # Search for similar issues first
    sys.stdout.write(f"Searching for similar issues...\n")
    similar = issues.search_similar(owner, repo, args.title)
    if similar:
        sys.stdout.write(f"Found {len(similar)} similar open issues:\n")
        for issue in similar[:5]:
            sys.stdout.write(f"  #{issue['number']}: {issue.get('title', '')}\n")
        sys.stdout.write("\n")

    # Create the issue
    body = issues.body_for("Task")
    ref = issues.create(owner, repo, args.title, body, args.issue_type, [])

    if args.area:
        # Add area label - in a real implementation we'd validate it exists
        pass

    # Get the NodeId for adding to the board
    try:
        node_id = ids.node_id(ref)
    except ids.MismatchedIssue as e:
        sys.stderr.write(f"capture: {e}\n")
        return 1

    # Add to board
    if not args.dry_run:
        try:
            board.add_item(cfg.project, node_id)
        except board.MissingScope:
            sys.stderr.write(
                "Projects v2 needs the project scope, which this token does not have.\n"
                "Run: gh auth refresh -s project\n"
            )
            return 1

        # Set status to triage
        fields_dict = board.fields(cfg.project)
        if "Status" in fields_dict:
            status_field = fields_dict["Status"]
            # Find the triage option
            for option in status_field.get("options", []):
                if option["name"] == cfg.triage_status:
                    board.set_field(cfg.project, node_id, status_field["id"], option["id"])
                    break

    sys.stdout.write(f"Created {ref}\n")
    return 0


def mode_review(args, cfg):
    """Read the dependency graph and propose new edges. Write only with confirmation."""
    # review mode would:
    # 1. Read all issues in the repo
    # 2. Build the dependency graph from blocked_by links
    # 3. Read memory (rejected additions, deliberate edges) for each issue
    # 4. Propose new edges based on reasoning
    # 5. Propose removals of edges
    # 6. Wait for user confirmation
    # 7. Record decisions in memory
    #
    # This requires enumeration of all open issues and user interaction,
    # which is agent-driven work, not CLI work. The agent's reasoning is
    # what produces the proposals.
    sys.stderr.write(
        "review: not yet implemented. This mode requires agent reasoning to "
        "propose edges, then user confirmation to record them.\n"
    )
    return 1


def mode_roadmap(args, cfg):
    """Build the dependency graph and render the roadmap."""
    try:
        owner, repo = _get_owner_repo(args.repo)
    except ValueError as e:
        sys.stderr.write(f"roadmap: {e}\n")
        return 1

    # roadmap mode would:
    # 1. Enumerate all open issues in the repo
    # 2. Read blocked_by links for each
    # 3. Build the graph
    # 4. Fetch titles for each issue
    # 5. Gather reasoning for each ordering decision (agent-provided)
    # 6. Identify issues in triage status
    # 7. Render and write to cfg.roadmap
    #
    # Step 1 (enumerate all issues) requires listing issues in a way the
    # current interfaces do not expose. board.items() lists issues on a
    # Projects v2 board, but not all open issues in the repo. A full
    # implementation would need to use gh search or gh issue list.
    sys.stderr.write(
        "roadmap: not yet implemented. Requires enumerating all open issues "
        "in the repo and gathering reasoning for each dependency.\n"
    )
    return 1


def mode_init(args, cfg):
    """Create the declared labels, fields and statuses. Idempotent."""
    # init mode would:
    # 1. Read declared labels from cfg.area_labels
    # 2. Create them if they don't exist (idempotent)
    # 3. Read declared fields (Effort, Risk) from cfg
    # 4. Create Projects v2 fields if they don't exist
    # 5. Create status options (Triage, etc.) if they don't exist
    #
    # This requires Repository mutation APIs that are not yet exposed by
    # the board module. A full implementation would use GraphQL mutations.
    sys.stderr.write(
        "init: not yet implemented. Requires Repository mutation APIs "
        "to create labels and Projects v2 field configurations.\n"
    )
    return 1


def mode_intake(args, cfg):
    """Add existing issues that are not on the board."""
    try:
        owner, repo = _get_owner_repo(args.repo)
    except ValueError as e:
        sys.stderr.write(f"intake: {e}\n")
        return 1

    try:
        board_items = board.items(cfg.project)
    except board.MissingScope:
        sys.stdout.write(
            "Projects v2 needs the project scope, which this token does not have.\n"
            "Run: gh auth refresh -s project\n"
        )
        return 1

    # Build a set of issues already on the board
    on_board = set()
    for item in board_items:
        if item.get("content"):
            content = item["content"]
            on_board.add(
                ids.Ref(
                    content["repository"]["owner"]["login"],
                    content["repository"]["name"],
                    ids.IssueNumber(content["number"]),
                )
            )

    # intake mode would:
    # 1. List all open issues in the repo (not yet implemented)
    # 2. Filter out those already on the board
    # 3. Add them to the board
    # 4. Optionally set status to a default
    #
    # Step 1 (list all issues) requires Repository API access that is
    # not yet exposed. A full implementation would use gh issue list or
    # GitHub REST API search.
    sys.stderr.write(
        f"intake: {len(on_board)} issues currently on the board. "
        "Listing all open issues in the repo is not yet implemented.\n"
    )
    return 1


def mode_doctor(args, cfg):
    """Report drift in configuration and board state."""
    try:
        # Try to fetch board fields to check if project scope is available
        board_fields = board.fields(cfg.project)
        board_items = board.items(cfg.project)
    except board.MissingScope:
        sys.stdout.write(
            "Projects v2 needs the project scope, which this token does not have.\n"
            "Run: gh auth refresh -s project\n"
        )
        return 0

    # doctor mode would:
    # 1. List all open issues in the repo
    # 2. Check each for required fields (Status, etc.)
    # 3. Check each for area labels if configured
    # 4. Report issues missing a field
    # 5. Report issues on the board but not open in the repo
    # 6. Report labels declared in config but not in the repo
    # 7. Report labels in the repo but not declared in config
    #
    # This is a health check - it reports drift but does not fix it.
    issues_on_board = len(board_items)
    sys.stdout.write(
        f"doctor: board has {issues_on_board} issues.\n"
        "Full drift report (repo labels, repo issues vs board) "
        "is not yet implemented.\n"
    )
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="deskwork")
    parser.add_argument("mode", choices=MODES)
    parser.add_argument("--repo", default=".", type=pathlib.Path)
    parser.add_argument("--title")
    parser.add_argument("--type", dest="issue_type")
    parser.add_argument("--area")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        cfg = config.load(args.repo)
    except config.ConfigError as error:
        # The file is there and it is wrong. A different exit code from the
        # gate, because this one is a mistake to fix rather than a repository
        # that simply has not opted in.
        sys.stderr.write(f"deskwork: {error}\n")
        return 3
    if cfg is None:
        sys.stderr.write(
            f"deskwork: {args.repo}/.github/deskwork.toml is missing, or does not "
            "carry enabled = true. deskwork does nothing in a repository that has "
            "not opted in.\n"
        )
        return 2

    return globals()[f"mode_{args.mode}"](args, cfg)


if __name__ == "__main__":
    sys.exit(main())
