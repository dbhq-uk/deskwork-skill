#!/usr/bin/env python3
"""deskwork - file what an agent notices, order it, and keep a roadmap in git.

This script never closes an issue, never deletes one, and never writes to any
repository without .github/deskwork.toml carrying enabled = true.
"""
import argparse
import datetime
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
    sys.stdout.write("Searching for similar issues...\n")
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
    try:
        owner, repo = _get_owner_repo(args.repo)
    except ValueError as e:
        sys.stderr.write(f"review: {e}\n")
        return 1

    # Get all open issues
    try:
        all_issues = issues.list_open(owner, repo)
    except gh.GhError as e:
        sys.stderr.write(f"review: failed to list issues: {e}\n")
        return 1

    # Build the existing dependency graph
    edges = {}
    for issue_ref in all_issues:
        ref = ids.Ref(owner, repo, ids.IssueNumber(issue_ref["number"]))
        edges[ref] = []

    # Get blocked_by relationships
    for issue_ref in all_issues:
        ref = ids.Ref(owner, repo, ids.IssueNumber(issue_ref["number"]))
        try:
            blockers = deps.blocked_by(ref)
            edges[ref] = blockers
        except ids.MismatchedIssue:
            pass  # Skip if the issue cannot be resolved

    # Read memory for each issue
    mem = {}
    for ref in edges:
        try:
            mem[ref] = memory.read(ref)
        except gh.GhError:
            mem[ref] = memory.Memory()

    # Build the graph
    g = graph.Graph(edges)

    # Present the graph and memory for review
    sys.stdout.write(f"review: {len(all_issues)} open issues, {len(g.ready())} ready\n")
    sys.stdout.write(f"review: {len(g.blocked())} blocked, {len(g.cycles())} cycles\n")
    for cycle in g.cycles():
        sys.stdout.write(f"  cycle: {' -> '.join(str(r) for r in cycle)}\n")

    # Note: The agent provides reasoning for proposals. This mode gathers
    # and presents the graph. Proposals and confirmation are agent work.
    sys.stdout.write("review: graph built. Agent reasoning would propose edges here.\n")
    return 0


def mode_roadmap(args, cfg):
    """Build the dependency graph and render the roadmap."""
    try:
        owner, repo = _get_owner_repo(args.repo)
    except ValueError as e:
        sys.stderr.write(f"roadmap: {e}\n")
        return 1

    # Get all open issues
    try:
        all_issues = issues.list_open(owner, repo)
    except gh.GhError as e:
        sys.stderr.write(f"roadmap: failed to list issues: {e}\n")
        return 1

    # Build the dependency graph
    edges = {}
    titles = {}
    reasons = {}
    for issue_ref in all_issues:
        ref = ids.Ref(owner, repo, ids.IssueNumber(issue_ref["number"]))
        edges[ref] = []
        titles[ref] = issue_ref.get("title", "")

    # Get blocked_by relationships for each issue
    for issue_ref in all_issues:
        ref = ids.Ref(owner, repo, ids.IssueNumber(issue_ref["number"]))
        try:
            blockers = deps.blocked_by(ref)
            edges[ref] = blockers
        except ids.MismatchedIssue:
            pass  # Skip if the issue cannot be resolved

    # Build the graph
    g = graph.Graph(edges)

    # Find issues in triage status (agent responsibility to set reasons)
    triage_issues = []
    try:
        board_items = board.items(cfg.project)
        triage_status = cfg.triage_status
        for item in board_items:
            if item.get("content"):
                content = item["content"]
                if content["repository"]["owner"]["login"] == owner and content["repository"]["name"] == repo:
                    # Check if this item is in triage status
                    for field_val in item.get("fieldValues", {}).get("nodes", []):
                        if field_val.get("field", {}).get("name") == "Status":
                            if field_val.get("name") == triage_status:
                                triage_issues.append(
                                    ids.Ref(
                                        content["repository"]["owner"]["login"],
                                        content["repository"]["name"],
                                        ids.IssueNumber(content["number"]),
                                    )
                                )
    except board.MissingScope:
        pass  # If no project scope, just skip triage detection

    # Render the roadmap
    generated = datetime.date.today()
    home = f"{owner}/{repo}"
    rendered = roadmap.render(g, titles, reasons, triage_issues, generated, len(all_issues), home)

    if args.dry_run:
        sys.stdout.write(rendered)
    else:
        path = args.repo / cfg.roadmap
        path.write_text(rendered)
        sys.stdout.write(f"roadmap: wrote {cfg.roadmap}\n")

    return 0


def mode_init(args, cfg):
    """Create the declared labels, fields and statuses. Idempotent."""
    try:
        owner, repo = _get_owner_repo(args.repo)
    except ValueError as e:
        sys.stderr.write(f"init: {e}\n")
        return 1

    created_count = 0

    # Create area labels
    for label_name in cfg.area_labels:
        if args.dry_run:
            sys.stdout.write(f"would create label: {label_name}\n")
        else:
            try:
                if issues.ensure_label(owner, repo, label_name, "000000", ""):
                    created_count += 1
                    sys.stdout.write(f"created label: {label_name}\n")
            except gh.GhError as e:
                sys.stderr.write(f"init: failed to create label {label_name}: {e}\n")
                return 1

    # Create Projects v2 fields
    try:
        for field_name, field_options in [
            ("Status", [cfg.triage_status] if cfg.triage_status else []),
            ("Effort", cfg.effort),
            ("Risk", cfg.risk),
        ]:
            if field_options:
                if args.dry_run:
                    sys.stdout.write(f"would create field: {field_name}\n")
                else:
                    try:
                        board.ensure_field(cfg.project, field_name, field_options)
                        created_count += 1
                        sys.stdout.write(f"created field: {field_name}\n")
                    except board.MissingScope:
                        sys.stdout.write(
                            "Projects v2 needs the project scope, which this token does not have.\n"
                            "Run: gh auth refresh -s project\n"
                        )
                        return 1
                    except gh.GhError as e:
                        sys.stderr.write(f"init: failed to create field {field_name}: {e}\n")
                        return 1
    except board.MissingScope:
        sys.stdout.write(
            "Projects v2 needs the project scope, which this token does not have.\n"
            "Run: gh auth refresh -s project\n"
        )
        return 1

    if args.dry_run:
        sys.stdout.write("(dry run - nothing written)\n")
    elif created_count > 0:
        sys.stdout.write(f"init: created {created_count} items\n")
    else:
        sys.stdout.write("init: everything already configured\n")

    return 0


def mode_intake(args, cfg):
    """Add existing issues that are not on the board."""
    try:
        owner, repo = _get_owner_repo(args.repo)
    except ValueError as e:
        sys.stderr.write(f"intake: {e}\n")
        return 1

    # Get all open issues
    try:
        all_issues = issues.list_open(owner, repo)
    except gh.GhError as e:
        sys.stderr.write(f"intake: failed to list issues: {e}\n")
        return 1

    # Get issues already on the board
    try:
        board_items = board.items(cfg.project)
    except board.MissingScope:
        sys.stdout.write(
            "Projects v2 needs the project scope, which this token does not have.\n"
            "Run: gh auth refresh -s project\n"
        )
        return 1

    on_board = set()
    for item in board_items:
        if item.get("content"):
            content = item["content"]
            if content["repository"]["owner"]["login"] == owner and content["repository"]["name"] == repo:
                on_board.add(ids.IssueNumber(content["number"]))

    # Find issues not on the board
    to_add = []
    for issue_ref in all_issues:
        if ids.IssueNumber(issue_ref["number"]) not in on_board:
            to_add.append(issue_ref)

    # Add them to the board
    added_count = 0
    for issue_ref in to_add:
        ref = ids.Ref(owner, repo, ids.IssueNumber(issue_ref["number"]))
        try:
            node_id = ids.node_id(ref)
            if args.dry_run:
                sys.stdout.write(f"would add {ref} to board\n")
            else:
                board.add_item(cfg.project, node_id)
                added_count += 1
                sys.stdout.write(f"added {ref}\n")
        except (ids.MismatchedIssue, gh.GhError) as e:
            sys.stderr.write(f"intake: failed to add {ref}: {e}\n")
            return 1

    if args.dry_run:
        sys.stdout.write(f"would add {len(to_add)} issues (dry run)\n")
    elif added_count > 0:
        sys.stdout.write(f"intake: added {added_count} issues\n")
    else:
        sys.stdout.write("intake: all issues already on board\n")

    return 0


def mode_doctor(args, cfg):
    """Report drift in configuration and board state."""
    try:
        owner, repo = _get_owner_repo(args.repo)
    except ValueError as e:
        sys.stderr.write(f"doctor: {e}\n")
        return 1

    # Get all open issues and board items
    try:
        all_issues = issues.list_open(owner, repo)
        board_items = board.items(cfg.project)
        board_fields = board.fields(cfg.project)
    except board.MissingScope:
        sys.stdout.write(
            "Projects v2 needs the project scope, which this token does not have.\n"
            "Run: gh auth refresh -s project\n"
        )
        return 0
    except gh.GhError as e:
        sys.stderr.write(f"doctor: failed to check board: {e}\n")
        return 1

    # Build set of issues on the board
    on_board = set()
    for item in board_items:
        if item.get("content"):
            content = item["content"]
            if content["repository"]["owner"]["login"] == owner and content["repository"]["name"] == repo:
                on_board.add(ids.IssueNumber(content["number"]))

    # Report issues not on board
    not_on_board = []
    for issue in all_issues:
        if ids.IssueNumber(issue["number"]) not in on_board:
            not_on_board.append(issue["number"])

    if not_on_board:
        sys.stdout.write(f"doctor: {len(not_on_board)} issues not on board\n")

    # Report field configuration
    sys.stdout.write(f"doctor: board has {len(board_items)} items, {len(all_issues)} open issues in repo\n")
    sys.stdout.write(f"doctor: configured fields: {', '.join(board_fields.keys())}\n")

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
