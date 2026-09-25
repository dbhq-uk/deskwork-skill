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


def _refs(text, home):
    """Refs from a comma-separated list: 5,6 or #5,owner/repo#9."""
    return [ids.parse(part, home) for part in str(text).split(",") if part.strip()]


def _capture_inputs(args, cfg):
    """(issue type to send, labels, body, parent, blockers), or None after saying why."""
    home = (args.owner, args.name)
    kind = args.issue_type or "Task"
    if cfg.issue_types and kind not in cfg.issue_types:
        sys.stderr.write(
            f"capture: --type {kind} is not one of this repository's configured types: "
            f"{', '.join(cfg.issue_types)}\n"
        )
        return None
    if args.area and args.area not in cfg.area_labels:
        configured = ", ".join(cfg.area_labels) or "none configured"
        sys.stderr.write(f"capture: --area {args.area} is not a configured area ({configured})\n")
        return None
    if not args.body_file:
        sys.stderr.write(
            "capture: --body-file is required (a path, or - for stdin). Start from "
            f"capture --template --type {kind} and fill every section.\n"
        )
        return None
    try:
        body = sys.stdin.read() if args.body_file == "-" else pathlib.Path(args.body_file).read_text()
    except OSError as error:
        sys.stderr.write(f"capture: cannot read the body: {error}\n")
        return None
    problems = issues.body_problems(kind, body)
    if problems:
        sys.stderr.write("capture: the body was refused, and nothing was filed.\n")
        for problem in problems:
            sys.stderr.write(f"  {problem}\n")
        return None
    labels = [cfg.triage_label] + ([cfg.area_label(args.area)] if args.area else [])
    try:
        parent = ids.parse(args.parent, home) if args.parent else None
        blockers = _refs(args.blocked_by, home) if args.blocked_by else []
    except ValueError as error:
        sys.stderr.write(f"capture: {error}\n")
        return None
    send_type = kind if cfg.issue_types else None
    return send_type, labels, body, parent, blockers


def mode_capture(args, cfg):
    """File a new issue in Triage, after checking for duplicates. Reads it back."""
    if args.template:
        sys.stdout.write(issues.body_for(args.issue_type or "Task") + "\n")
        return 0
    if not (args.title or "").strip():
        sys.stderr.write("capture: --title is required\n")
        return 1
    inputs = _capture_inputs(args, cfg)
    if inputs is None:
        return 1
    send_type, labels, body, parent, blockers = inputs
    title = args.title.strip()

    if not args.file:
        try:
            candidates, warning = issues.duplicate_candidates(args.owner, args.name, title)
        except gh.GhError as error:
            sys.stderr.write(f"capture: cannot list open issues to check for duplicates: {error}\n")
            return 1
        if warning:
            sys.stderr.write(f"capture: {warning}\n")
        if candidates:
            sys.stdout.write(json.dumps({
                "filed": False,
                "candidates": candidates,
                "next": "Read each candidate. If one is this issue, comment on it instead. "
                        "If none is, run the same command again with --file.",
            }, indent=2) + "\n")
            return 10

    if args.dry_run:
        sys.stdout.write(json.dumps({
            "filed": False, "dry_run": True, "title": title, "type": send_type,
            "labels": labels, "parent": str(parent) if parent else None,
            "blocked_by": [str(b) for b in blockers],
            "board": cfg.project, "status": cfg.triage_status if cfg.project else None,
            "body": body,
        }, indent=2) + "\n")
        return 0

    try:
        ref = issues.create(args.owner, args.name, title, body, send_type, labels, parent, blockers)
    except (gh.GhError, ValueError) as error:
        sys.stderr.write(f"capture: gh did not file the issue: {error}\n")
        return 1
    home = (args.owner, args.name)
    filed = f"capture: filed {ref.short(home)} https://github.com/{ref.owner}/{ref.repo}/issues/{int(ref.number)}"
    sys.stdout.write(filed + "\n")
    retry = f"{ref.short(home)} exists now. Do not file it again; fix what is wrong on it by hand."
    try:
        node, problems = issues.check_filed(ref, title, body, send_type, labels, parent, blockers)
    except (gh.GhError, ids.MismatchedIssue) as error:
        sys.stderr.write(f"capture: could not read {ref.short(home)} back: {error}. {retry}\n")
        return 4
    if problems:
        sys.stderr.write(f"capture: {ref.short(home)} is not as asked: {'; '.join(problems)}. {retry}\n")
        return 4

    if cfg.project:
        try:
            item = board.add_item(cfg.project, node)
            board.set_status(cfg.project, item, cfg.triage_status)
        except board.MissingScope as error:
            sys.stderr.write(f"capture: {error}. {retry}\n")
            return 4
        except (board.NotConfirmed, gh.GhError) as error:
            sys.stderr.write(f"capture: the board step failed: {error}. {retry}\n")
            return 4
        sys.stdout.write(f"capture: on the board with Status {cfg.triage_status}, read back\n")
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
    """Create the labels capture applies, and the Triage option on the board.

    Idempotent. Reports only what it created, and reads each write back.
    """
    wanted = {cfg.triage_label: (issues.TRIAGE_COLOUR, "Filed by an agent and not yet reviewed")}
    for area in cfg.area_labels:
        wanted[cfg.area_label(area)] = (issues.AREA_COLOUR, f"Area: {area}")
    try:
        have = issues.repo_labels(args.owner, args.name)
    except gh.GhError as error:
        sys.stderr.write(f"init: cannot list labels: {error}\n")
        return 1
    missing = [label for label in wanted if label not in have]

    add_option = False
    if cfg.project:
        try:
            status = board.fields(cfg.project).get("Status") or {}
        except board.MissingScope as error:
            sys.stderr.write(f"init: {error}\n")
            return 1
        except gh.GhError as error:
            sys.stderr.write(f"init: cannot read the board: {error}\n")
            return 1
        add_option = not any(o["name"] == cfg.triage_status for o in status.get("options", []))

    if args.dry_run:
        for label in missing:
            sys.stdout.write(f"init: would create label {label}\n")
        if add_option:
            sys.stdout.write(f"init: would add the {cfg.triage_status} option to Status on {cfg.project}\n")
        if not missing and not add_option:
            sys.stdout.write("init: nothing to create\n")
        return 0

    created = []
    for label in missing:
        colour, description = wanted[label]
        try:
            issues.create_label(args.owner, args.name, label, colour, description)
        except gh.GhError as error:
            sys.stderr.write(f"init: could not create label {label}: {error}\n")
            return 1
        created.append(f"label {label}")
    if missing:
        still = [label for label in missing if label not in issues.repo_labels(args.owner, args.name)]
        if still:
            sys.stderr.write(f"init: labels not there after creating them: {', '.join(still)}\n")
            return 4
    if add_option:
        try:
            if board.ensure_status_option(cfg.project, cfg.triage_status):
                created.append(f"the {cfg.triage_status} option on Status")
        except (board.MissingScope, board.NotConfirmed, gh.GhError) as error:
            sys.stderr.write(f"init: {error}\n")
            return 4

    if created:
        for item in created:
            sys.stdout.write(f"init: created {item}\n")
    else:
        sys.stdout.write("init: nothing to create, everything is in place\n")
    return 0


def mode_intake(args, cfg):
    """Put open issues that are not on the board onto it. Needs a board."""
    if not cfg.project:
        sys.stdout.write("intake: no board configured (project is not set), so nothing to do\n")
        return 0
    try:
        open_now = issues.open_issues(args.owner, args.name)
        on_board = {ref for ref, _, _ in board.items(cfg.project)}
    except board.MissingScope as error:
        sys.stderr.write(f"intake: {error}\n")
        return 1
    except gh.GhError as error:
        sys.stderr.write(f"intake: {error}\n")
        return 1
    to_add = [(ref, node) for ref, node in open_now if ref not in on_board]
    home = (args.owner, args.name)
    if args.dry_run or not to_add:
        for ref, _ in to_add:
            sys.stdout.write(f"intake: would add {ref.short(home)}\n")
        if not to_add:
            sys.stdout.write("intake: every open issue is already on the board\n")
        return 0
    for ref, node in to_add:
        try:
            board.add_item(cfg.project, node)
        except (board.MissingScope, gh.GhError) as error:
            sys.stderr.write(f"intake: could not add {ref.short(home)}: {error}\n")
            return 1
    now_on = {ref for ref, _, _ in board.items(cfg.project)}
    absent = [ref.short(home) for ref, _ in to_add if ref not in now_on]
    if absent:
        sys.stderr.write(f"intake: not on the board after adding: {', '.join(absent)}\n")
        return 4
    sys.stdout.write(f"intake: added {len(to_add)} issues, read back from the board\n")
    return 0


def mode_doctor(args, cfg):
    """Report drift between the config, the labels, the types and the board.

    Exits 1 on any drift. The gh version was checked before this ran.
    """
    home = (args.owner, args.name)
    problems, notes = [], [f"gh {'.'.join(map(str, gh.version()))}, repository {args.owner}/{args.name}"]
    try:
        have = issues.repo_labels(args.owner, args.name)
    except gh.GhError as error:
        problems.append(f"cannot list labels: {error}")
        have = None
    if have is not None:
        for label in cfg.labels:
            if label not in have:
                problems.append(f"label {label} is in the config and not in the repository. Run init.")
        for label in sorted(have):
            if label.startswith("area:") and label[5:] not in cfg.area_labels:
                problems.append(f"label {label} is in the repository and not in the config's areas.")
    if cfg.issue_types:
        try:
            enabled = issues.repo_issue_types(args.owner, args.name)
        except gh.GhError as error:
            problems.append(f"cannot read the issue types: {error}")
            enabled = None
        if enabled is not None and not enabled:
            problems.append("this repository has no issue types. Set issue_types = [] in the config.")
        elif enabled is not None:
            for kind in cfg.issue_types:
                if kind not in enabled:
                    problems.append(f"issue type {kind} is in the config and not enabled for this repository.")
    if cfg.project:
        try:
            status = board.fields(cfg.project).get("Status")
            on_board = {ref for ref, _, _ in board.items(cfg.project)}
            open_now = issues.open_issues(args.owner, args.name)
        except board.MissingScope as error:
            problems.append(str(error))
        except gh.GhError as error:
            problems.append(f"cannot read the board: {error}")
        else:
            if not status or not any(o["name"] == cfg.triage_status for o in status.get("options", [])):
                problems.append(f"the board's Status field has no {cfg.triage_status} option. Run init.")
            absent = [ref.short(home) for ref, _ in open_now if ref not in on_board]
            if absent:
                problems.append(f"{len(absent)} open issues are not on the board: {', '.join(absent)}. Run intake.")
    else:
        notes.append("no board configured, so Triage is the label alone")
    for note in notes:
        sys.stdout.write(f"doctor: {note}\n")
    for problem in problems:
        sys.stdout.write(f"doctor: DRIFT {problem}\n")
    if problems:
        sys.stdout.write(f"doctor: {len(problems)} problems\n")
        return 1
    sys.stdout.write("doctor: no drift\n")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="deskwork")
    parser.add_argument("mode", choices=MODES)
    parser.add_argument("issue", nargs="?", help="the issue a link, unlink, reject or keep is about")
    parser.add_argument("--repo", default=".", type=pathlib.Path)
    parser.add_argument("--title")
    parser.add_argument("--type", dest="issue_type")
    parser.add_argument("--area")
    parser.add_argument("--blocked-by", help="the blocking issue: 12, #12, owner/repo#12 or a URL "
                        "(capture takes a comma-separated list)")
    parser.add_argument("--body-file", help="capture: the body, from a file or - for stdin")
    parser.add_argument("--template", action="store_true", help="capture: print the body sections for --type")
    parser.add_argument("--parent", help="capture: file the issue as a sub-issue of this one")
    parser.add_argument("--file", action="store_true", help="capture: file even though duplicates were found")
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

    if args.mode == "init" and not config.exists(args.root):
        # The one write allowed before the gate: a starter that is off.
        if args.dry_run:
            sys.stdout.write(f"init: would write {config.CONFIG_PATH} with enabled = false\n")
            return 0
        path = config.write_starter(args.root)
        sys.stdout.write(
            f"init: wrote {path.relative_to(args.root).as_posix()} with enabled = false. "
            "Edit it, set enabled = true, commit it, then run init again to create "
            "the labels.\n"
        )
        return 0

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
            "not opted in. init writes a starter file, switched off.\n"
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
