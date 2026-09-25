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
import git
import graph
import ids
import issues
import memory
import repo
import roadmap

MODES = (
    "capture", "review", "link", "unlink", "reject", "keep",
    "roadmap", "init", "intake", "doctor",
)


def mode_capture(args, cfg):
    """File a new issue: duplicate search, create, add to board, set to Triage."""
    if not args.title:
        sys.stderr.write("capture: --title is required\n")
        return 1

    owner, repo = args.owner, args.name

    # Search for similar issues first (read only, always safe)
    sys.stdout.write("Searching for similar issues...\n")
    similar = issues.search_similar(owner, repo, args.title)
    if similar:
        sys.stdout.write(f"Found {len(similar)} similar open issues:\n")
        for issue in similar[:5]:
            sys.stdout.write(f"  #{issue['number']}: {issue.get('title', '')}\n")
        sys.stdout.write("\n")

    # Prepare the issue body
    body = issues.body_for("Task")
    labels = []
    if args.area:
        labels.append(f"area:{args.area}")

    # Check dry-run before any write
    if args.dry_run:
        sys.stdout.write("Would create issue:\n")
        sys.stdout.write(f"  Title: {args.title}\n")
        if args.issue_type:
            sys.stdout.write(f"  Type: {args.issue_type}\n")
        if labels:
            sys.stdout.write(f"  Labels: {', '.join(labels)}\n")
        sys.stdout.write("  Body:\n")
        for line in body.split("\n"):
            sys.stdout.write(f"    {line}\n")
        sys.stdout.write(f"  Project: {cfg.project}\n")
        sys.stdout.write(f"  Status: {cfg.triage_status}\n")
        return 0

    # Perform the actual writes
    # Create the issue
    ref = issues.create(owner, repo, args.title, body, args.issue_type, labels)

    # Get the NodeId for adding to the board
    try:
        node_id = ids.node_id(ref)
    except ids.MismatchedIssue as e:
        sys.stderr.write(f"capture: {e}\n")
        return 1

    # Add to board
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


def _home(args):
    return (args.owner, args.name)


def _read_graph(args, cfg, mode, with_memory=False):
    """Every open issue, or None after saying why it could not be read."""
    try:
        return issues.read_graph(args.owner, args.name, cfg.project, with_memory)
    except gh.GhError as error:
        if "read:project" in str(error) or "required scopes" in str(error):
            sys.stderr.write(
                f"{mode}: reading the board needs the project scope. "
                "Run: gh auth refresh -s project\n"
            )
        else:
            sys.stderr.write(f"{mode}: cannot read the issues: {error}\n")
    except issues.IncompleteRead as error:
        sys.stderr.write(f"{mode}: {error}. Refusing to work from a partial graph.\n")
    return None


def _shape(found, cfg):
    """(graph, triage, ready, blocked) for the open issues in found.

    A closed blocker blocks nothing, and a Triage issue is neither ready nor
    blocked: it is unreviewed, and lives only under Triage.
    """
    edges = {issue.ref: set(issue.open_blockers) for issue in found}
    g = graph.Graph(edges)
    triage, ready, blocked = [], [], []
    for issue in sorted(found, key=lambda i: int(i.ref.number)):
        if issue.in_triage(cfg.triage_label, cfg.project and cfg.triage_status):
            triage.append(issue.ref)
        elif issue.open_blockers:
            blocked.append(issue.ref)
        else:
            ready.append(issue.ref)
    return g, triage, ready, blocked


def mode_review(args, cfg):
    """Print the graph for the agent to reason over. Writes nothing."""
    found = _read_graph(args, cfg, "review", with_memory=True)
    if found is None:
        return 1
    home = _home(args)
    g, triage, ready, blocked = _shape(found, cfg)

    def short(refs):
        return [ref.short(home) for ref in refs]

    report = {
        "repository": f"{args.owner}/{args.name}",
        "open_issues": len(found),
        "issues": [
            {
                "ref": issue.ref.short(home),
                "title": issue.title,
                "type": issue.type,
                "labels": issue.labels,
                "triage": issue.ref in triage,
                "parent": issue.parent.short(home) if issue.parent else None,
                "blocked_by": [
                    {"ref": b.ref.short(home), "state": b.state, "title": b.title}
                    for b in issue.blockers
                ],
                "memory": memory.as_json(issue.memory or memory.Memory(), home),
            }
            for issue in sorted(found, key=lambda i: int(i.ref.number))
        ],
        "ready": short(ready),
        "blocked": short(blocked),
        "triage": short(triage),
        "cycles": [short(cycle) for cycle in g.cycles()],
        "bottlenecks": [{"ref": ref.short(home), "blocks": n} for ref, n in g.bottlenecks()],
    }
    if args.json:
        sys.stdout.write(json.dumps(report, indent=2) + "\n")
        return 0

    out = [f"review: {report['repository']}, {len(found)} open issues"]
    for item in report["issues"]:
        flag = " [triage]" if item["triage"] else ""
        out.append(f"{item['ref']} {item['title']}{flag}")
        for b in item["blocked_by"]:
            out.append(f"    blocked by {b['ref']} ({b['state'].lower()}) {b['title']}".rstrip())
        for m in item["memory"]:
            out.append(f"    remembered: {m['decision']} {m['ref']} {m['note']}".rstrip())
    out.append(f"ready: {', '.join(report['ready']) or 'none'}")
    out.append(f"blocked: {', '.join(report['blocked']) or 'none'}")
    out.append(f"triage: {', '.join(report['triage']) or 'none'}")
    for cycle in report["cycles"]:
        out.append(f"cycle: {' -> '.join(cycle)}")
    for b in report["bottlenecks"]:
        out.append(f"bottleneck: {b['ref']} blocks {b['blocks']} issues")
    sys.stdout.write("\n".join(out) + "\n")
    return 0


def _edge_args(args, verb):
    """(ref, blocker) from `VERB 12 --blocked-by 5 --reason "..."`, or None."""
    if not args.issue or not args.blocked_by:
        sys.stderr.write(f'{verb}: usage: {verb} ISSUE --blocked-by ISSUE --reason "why"\n')
        return None
    if not (args.reason or "").strip():
        sys.stderr.write(f"{verb}: --reason is required. The reason is recorded on the issue.\n")
        return None
    try:
        ref = ids.parse(args.issue, _home(args))
        blocker = ids.parse(args.blocked_by, _home(args))
    except ValueError as error:
        sys.stderr.write(f"{verb}: {error}\n")
        return None
    if (ref.owner, ref.repo) != _home(args):
        sys.stderr.write(f"{verb}: {ref} is in another repository. deskwork edits this repository's issues only.\n")
        return None
    if ref == blocker:
        sys.stderr.write(f"{verb}: an issue cannot block itself.\n")
        return None
    return ref, blocker


def _edge_verb(args, verb):
    """link, unlink, reject and keep: one edge, one decision, one reason.

    Run only after a human has approved the decision. The graph write, if any,
    is read back; so is the memory comment that records the reason.
    """
    parsed = _edge_args(args, verb)
    if parsed is None:
        return 1
    ref, blocker = parsed
    home = _home(args)
    edge = f"{ref.short(home)} blocked by {blocker.short(home)}"
    try:
        current = {b.ref for b in deps.blocked_by(ref)}
    except (gh.GhError, deps.WriteNotConfirmed, ids.MismatchedIssue) as error:
        sys.stderr.write(f"{verb}: cannot read {ref.short(home)}: {error}\n")
        return 1
    if verb == "reject" and blocker in current:
        sys.stderr.write(f"reject: {edge} already exists. To remove it, use unlink.\n")
        return 1
    if verb == "keep" and blocker not in current:
        sys.stderr.write(f"keep: {edge} does not exist, so there is nothing to keep.\n")
        return 1
    decision = {"link": "linked", "unlink": "unlinked", "reject": "rejected", "keep": "deliberate"}[verb]
    if args.dry_run:
        write = {"link": "add the edge", "unlink": "remove the edge"}.get(verb, "leave the graph alone")
        sys.stdout.write(f"{verb}: would {write} ({edge}) and record '{decision}: {args.reason}'\n")
        return 0
    try:
        if verb == "link":
            changed = deps.link(ref, blocker)
        elif verb == "unlink":
            changed = deps.unlink(ref, blocker)
        else:
            changed = False
    except deps.WriteNotConfirmed as error:
        sys.stderr.write(f"{verb}: not confirmed. {error}\n")
        return 4
    except gh.GhError as error:
        sys.stderr.write(f"{verb}: gh refused the write: {error}\n")
        return 1
    if verb in ("link", "unlink"):
        sys.stdout.write(
            f"{verb}: {edge} {'written and read back' if changed else 'was already so'}\n"
        )
    try:
        memory.record(ref, decision, blocker, args.reason)
    except (memory.WriteNotConfirmed, gh.GhError) as error:
        sys.stderr.write(f"{verb}: the reason was not recorded on {ref.short(home)}: {error}\n")
        return 4
    sys.stdout.write(f"{verb}: recorded on {ref.short(home)}: {decision}: {blocker.short(home)} {args.reason}\n")
    return 0


def mode_link(args, cfg):
    return _edge_verb(args, "link")


def mode_unlink(args, cfg):
    return _edge_verb(args, "unlink")


def mode_reject(args, cfg):
    return _edge_verb(args, "reject")


def mode_keep(args, cfg):
    return _edge_verb(args, "keep")


def _state_of(ref):
    return gh.run_json(
        ["issue", "view", str(int(ref.number)), "-R", ref.repo_arg, "--json", "state"]
    )["state"]


def _commit_roadmap(root, relative, issue_count):
    """Commit the roadmap file alone, then check the commit holds nothing else."""
    if not git.run(["status", "--porcelain", "--", relative], cwd=root).strip():
        return None
    git.run(["add", "--", relative], cwd=root)
    git.run(
        ["commit", "--only", "-m", f"docs(roadmap): refresh from {issue_count} open issues",
         "--", relative],
        cwd=root,
    )
    out = git.run(["log", "-1", "--format=%h", "--name-only"], cwd=root).split()
    commit, files = out[0], out[1:]
    if files != [relative]:
        raise git.GitError(f"commit {commit} touched {files}, expected only {relative}")
    return commit


def mode_roadmap(args, cfg):
    """Check the agent's order against the graph, render roadmap.md, commit it."""
    home = _home(args)
    entries = []
    if args.order:
        try:
            text = sys.stdin.read() if args.order == "-" else pathlib.Path(args.order).read_text()
            entries, problems = roadmap.load_order(text, home)
        except (OSError, roadmap.OrderError) as error:
            sys.stderr.write(f"roadmap: {error}\n")
            return 1
    elif not args.dry_run:
        sys.stderr.write(
            "roadmap: --order is required to write the roadmap: a JSON list of "
            '{"ref": "#12", "reason": "why it is next"}, reasoned from review --json. '
            "Use --dry-run to preview without one.\n"
        )
        return 1
    else:
        problems = []

    found = _read_graph(args, cfg, "roadmap")
    if found is None:
        return 1
    g, triage, ready, blocked = _shape(found, cfg)
    by_ref = {issue.ref: issue for issue in found}
    problems += roadmap.check_order(entries, by_ref, set(triage), home, _state_of)
    if problems:
        sys.stderr.write("roadmap: the order was refused, and nothing was written.\n")
        for problem in problems:
            sys.stderr.write(f"  {problem}\n")
        return 1

    ordered = {ref for ref, _ in entries}
    titles = {issue.ref: issue.title for issue in found}
    for issue in found:
        for b in issue.blockers:
            titles.setdefault(b.ref, b.title)
    rendered = roadmap.render(
        home=home,
        generated=datetime.date.today(),
        issue_count=len(found),
        order=entries,
        blocked=[(ref, by_ref[ref].open_blockers) for ref in blocked],
        later=[ref for ref in ready if ref not in ordered],
        triage=triage,
        graph=g,
        titles=titles,
    )
    if args.dry_run:
        sys.stdout.write(rendered)
        return 0

    path = args.root / cfg.roadmap
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered)
    relative = path.relative_to(args.root).as_posix()
    try:
        commit = _commit_roadmap(args.root, relative, len(found))
    except git.GitError as error:
        sys.stderr.write(f"roadmap: wrote {relative} and could not commit it: {error}\n")
        return 1
    if commit is None:
        sys.stdout.write(f"roadmap: {relative} is unchanged, nothing to commit\n")
    else:
        sys.stdout.write(f"roadmap: wrote {relative} and committed it alone as {commit}\n")
    return 0


def mode_init(args, cfg):
    """Create the declared labels, fields and statuses. Idempotent."""
    owner, repo = args.owner, args.name

    # Check dry-run before any writes
    if args.dry_run:
        sys.stdout.write("Would create:\n")
        for label_name in cfg.area_labels:
            sys.stdout.write(f"  label: {label_name}\n")
        for field_name, field_options in [
            ("Status", [cfg.triage_status] if cfg.triage_status else []),
            ("Effort", cfg.effort),
            ("Risk", cfg.risk),
        ]:
            if field_options:
                sys.stdout.write(f"  field: {field_name} with options {field_options}\n")
        sys.stdout.write("(dry run - nothing written)\n")
        return 0

    created_count = 0

    # Create area labels
    for label_name in cfg.area_labels:
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

    if created_count > 0:
        sys.stdout.write(f"init: created {created_count} items\n")
    else:
        sys.stdout.write("init: everything already configured\n")

    return 0


def mode_intake(args, cfg):
    """Add existing issues that are not on the board."""
    owner, repo = args.owner, args.name

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

    # Check dry-run before any writes
    if args.dry_run:
        sys.stdout.write(f"Would add {len(to_add)} issues to board:\n")
        for issue_ref in to_add:
            ref = ids.Ref(owner, repo, ids.IssueNumber(issue_ref["number"]))
            sys.stdout.write(f"  {ref}\n")
        return 0

    # Add them to the board
    added_count = 0
    for issue_ref in to_add:
        ref = ids.Ref(owner, repo, ids.IssueNumber(issue_ref["number"]))
        try:
            node_id = ids.node_id(ref)
            board.add_item(cfg.project, node_id)
            added_count += 1
            sys.stdout.write(f"added {ref}\n")
        except (ids.MismatchedIssue, gh.GhError) as e:
            sys.stderr.write(f"intake: failed to add {ref}: {e}\n")
            return 1

    if added_count > 0:
        sys.stdout.write(f"intake: added {added_count} issues\n")
    else:
        sys.stdout.write("intake: all issues already on board\n")

    return 0


def mode_doctor(args, cfg):
    """Report drift in configuration and board state."""
    owner, repo = args.owner, args.name

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
    parser.add_argument("issue", nargs="?", help="the issue a link, unlink, reject or keep is about")
    parser.add_argument("--repo", default=".", type=pathlib.Path)
    parser.add_argument("--title")
    parser.add_argument("--type", dest="issue_type")
    parser.add_argument("--area")
    parser.add_argument("--blocked-by", help="the blocking issue: 12, #12, owner/repo#12 or a URL")
    parser.add_argument("--reason", help="why, recorded on the issue")
    parser.add_argument("--order", help='roadmap: JSON file (or - for stdin) of {"ref", "reason"}')
    parser.add_argument("--json", action="store_true", help="review: print JSON")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        args.root = repo.root(args.repo)
    except repo.NotARepo as error:
        sys.stderr.write(f"deskwork: {error}\n")
        return 1

    try:
        cfg = config.load(args.root)
    except config.ConfigError as error:
        # The file is there and it is wrong. A different exit code from the
        # gate, because this one is a mistake to fix rather than a repository
        # that simply has not opted in.
        sys.stderr.write(f"deskwork: {error}\n")
        return 3
    if cfg is None:
        sys.stderr.write(
            f"deskwork: {args.root}/{config.CONFIG_PATH} is missing, or does not "
            "carry enabled = true. deskwork does nothing in a repository that has "
            "not opted in.\n"
        )
        return 2

    try:
        gh.require_version()
        args.owner, args.name = repo.name_with_owner(args.root)
    except gh.TooOld as error:
        sys.stderr.write(f"deskwork: {error}\n")
        return 1
    except (gh.GhError, ValueError) as error:
        sys.stderr.write(f"deskwork: cannot tell which GitHub repository this is: {error}\n")
        return 1

    return globals()[f"mode_{args.mode}"](args, cfg)


if __name__ == "__main__":
    sys.exit(main())
