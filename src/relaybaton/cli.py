"""Command-line interface: ``baton``.

Exit codes: 0 = all good, 1 = a check found a problem, 2 = usage or config error.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import TextIO

from relaybaton import __version__, config, handoff, ownership, sync

OK, PROBLEM, ERROR = 0, 1, 2


def _today(value: str | None) -> date:
    return date.fromisoformat(value) if value else date.today()


def _iso_date(value: str) -> str:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {value!r}") from exc
    return value


def _agent_name(value: str) -> str:
    name = value.strip().removeprefix("@").strip()
    if not name:
        raise argparse.ArgumentTypeError("expected an agent name, got an empty string")
    return name


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected a positive whole number, got {value!r}") from exc
    if number < 1:
        raise argparse.ArgumentTypeError(f"expected a positive whole number, got {value!r}")
    return number


SHALLOW_HINT = (
    " (comparing with --base needs the branch history; in GitHub Actions use "
    "actions/checkout with fetch-depth: 0)"
)


def _emit_json(payload: dict, out: TextIO) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True), file=out)


def _targets_json(statuses: list[sync.TargetStatus]) -> list[dict]:
    return [{"agent": s.agent, "path": s.path, "state": s.state.value} for s in statuses]


def _status_json(st: handoff.HandoffStatus, file: str) -> dict:
    return {
        "file": file,
        "exists": st.exists,
        "entries": st.entries,
        "newest": st.newest.isoformat() if st.newest else None,
        "age_days": st.age_days,
        "max_age_days": st.max_age_days,
        "future_dated": st.future,
        "stale": st.stale,
        "healthy": st.healthy,
    }


def _task_json(task: handoff.Task, today: date) -> dict:
    return {"date": task.day.isoformat(), "entry": task.entry, "text": task.text, "age_days": task.age(today)}


# ---------------------------------------------------------------- commands


def cmd_init(args: argparse.Namespace, out: TextIO) -> int:
    root = Path(args.directory).resolve()
    created = []
    cfg_path = root / config.CONFIG_NAME
    if cfg_path.exists() and not args.force:
        print(f"{config.CONFIG_NAME} already exists (use --force to overwrite)", file=out)
        return ERROR
    cfg_path.write_text(config.TEMPLATE, encoding="utf-8")
    created.append(config.CONFIG_NAME)

    agents = root / "AGENTS.md"
    if not agents.exists():
        agents.write_text(
            "# Project instructions for AI coding agents\n\n"
            "Describe how to build, test and contribute here. "
            "Every agent-specific file is generated from this one.\n",
            encoding="utf-8",
        )
        created.append("AGENTS.md")
    log = root / "HANDOFF.md"
    if not log.exists():
        log.write_text(handoff.TEMPLATE, encoding="utf-8")
        created.append("HANDOFF.md")
    for name in created:
        print(f"created {name}", file=out)
    print("next: edit AGENTS.md, then run `baton sync`", file=out)
    return OK


def cmd_sync(args: argparse.Namespace, out: TextIO) -> int:
    cfg = config.load(Path(args.directory))
    statuses = sync.write(cfg, force=args.force)
    skipped = 0
    for status in statuses:
        if status.state is sync.State.OK:
            print(f"  ok        {status.path}", file=out)
        elif status.state is sync.State.UNMANAGED and not args.force:
            skipped += 1
            print(f"  skipped   {status.path} (hand-written; --force to replace)", file=out)
        else:
            print(f"  wrote     {status.path} ({status.state.value})", file=out)
    return PROBLEM if skipped else OK


def cmd_check(args: argparse.Namespace, out: TextIO) -> int:
    cfg = config.load(Path(args.directory))
    statuses = sync.plan(cfg)
    bad = [s for s in statuses if s.state is not sync.State.OK]
    if args.json:
        _emit_json({"ok": not bad, "source": cfg.source, "targets": _targets_json(statuses)}, out)
        return PROBLEM if bad else OK
    for status in statuses:
        label = "ok" if status.state is sync.State.OK else status.state.value.upper()
        print(f"  {label:<10}{status.path}", file=out)
        if args.diff and status.state is not sync.State.OK:
            print(status.diff() or "  (file is missing)", file=out)
    if bad:
        print(f"{len(bad)} target(s) out of date: run `baton sync`", file=out)
        return PROBLEM
    print(f"all {len(statuses)} target(s) match {cfg.source}", file=out)
    return OK


def _read_message(parts: list[str]) -> str:
    if not parts or parts == ["-"]:
        if sys.stdin.isatty() and not parts:
            raise ValueError("give a message, or pipe one in and pass -")
        return sys.stdin.read()
    return " ".join(parts)


def cmd_handoff_add(args: argparse.Namespace, out: TextIO) -> int:
    cfg = config.load(Path(args.directory))
    try:
        message = _read_message(args.message)
        entry = handoff.add_entry(
            cfg.path(cfg.handoff.file),
            author=args.author,
            message=message,
            day=_today(args.date),
            to=args.to,
            subject=args.subject,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=out)
        return ERROR
    print(f"added {entry.day.isoformat()} — {entry.title} to {cfg.handoff.file}", file=out)
    return OK


def _print_status(st: handoff.HandoffStatus, file: str, out: TextIO) -> None:
    if not st.exists:
        print(f"  MISSING   {file} (run `baton init` or `baton handoff add`)", file=out)
    elif st.newest is None:
        print(f"  STALE     {file} has no dated entries", file=out)
    else:
        label = "STALE" if st.stale else "ok"
        print(
            f"  {label:<10}{file}: newest entry {st.newest.isoformat()}, "
            f"{st.age_days} day(s) old (limit {st.max_age_days}), {st.entries} entries",
            file=out,
        )
    if st.future:
        print(f"  INVALID   {st.future} entry(ies) dated in the future; fix the date(s)", file=out)


def cmd_handoff_status(args: argparse.Namespace, out: TextIO) -> int:
    cfg = config.load(Path(args.directory))
    max_age = args.max_age or cfg.handoff.max_age_days
    st = handoff.status(cfg.path(cfg.handoff.file), max_age, _today(args.today))
    if args.json:
        _emit_json(_status_json(st, cfg.handoff.file), out)
    else:
        _print_status(st, cfg.handoff.file, out)
    return OK if st.healthy else PROBLEM


def cmd_handoff_open(args: argparse.Namespace, out: TextIO) -> int:
    cfg = config.load(Path(args.directory))
    today = _today(args.today)
    agent = args.agent
    pending = handoff.open_tasks(cfg.path(cfg.handoff.file), agent)
    overdue = [t for t in pending if args.max_age and t.age(today) >= args.max_age]
    if args.json:
        _emit_json(
            {
                "tasks": [_task_json(t, today) for t in pending],
                "for": agent,
                "max_age_days": args.max_age,
                "overdue": len(overdue),
            },
            out,
        )
        return PROBLEM if overdue else OK
    for_agent = f" for {agent}" if agent else ""
    if not pending:
        print(f"no open tasks{for_agent} in the handoff log", file=out)
        return OK
    for task in pending:
        label = "OVERDUE" if task in overdue else "open"
        print(f"  {label:<10}{task.day.isoformat()}  {task.text}  ({task.entry})", file=out)
    summary = f"{len(pending)} open task(s){for_agent}"
    if args.max_age:
        summary += f", {len(overdue)} at least {args.max_age} day(s) old"
    print(summary, file=out)
    return PROBLEM if overdue else OK


def cmd_handoff_list(args: argparse.Namespace, out: TextIO) -> int:
    cfg = config.load(Path(args.directory))
    path = cfg.path(cfg.handoff.file)
    if not path.exists():
        print(f"{cfg.handoff.file} does not exist", file=out)
        return PROBLEM
    entries = sorted(handoff.parse(path.read_text(encoding="utf-8")), key=lambda e: e.day, reverse=True)
    for entry in entries[: args.n]:
        first_line = entry.body.splitlines()[0] if entry.body else ""
        print(f"{entry.day.isoformat()}  {entry.title}", file=out)
        if first_line:
            print(f"            {first_line[:100]}", file=out)
    return OK


def cmd_guard(args: argparse.Namespace, out: TextIO) -> int:
    cfg = config.load(Path(args.directory))
    if not cfg.ownership:
        print("no [ownership] rules configured; nothing to guard", file=out)
        return OK
    try:
        files = args.files or ownership.changed_files(cfg.root, args.base)
    except ownership.GitError as exc:
        hint = SHALLOW_HINT if args.base and "no commits" not in str(exc) else ""
        print(f"error: {exc}{hint}", file=out)
        return ERROR
    violations = ownership.check(files, args.agent, cfg.ownership)
    for v in violations:
        print(f"  BLOCKED   {v.path} is owned by {v.owner}, not {args.agent}", file=out)
    if violations:
        print(f"{len(violations)} file(s) belong to another agent: hand them off instead", file=out)
        return PROBLEM
    print(f"  ok        {len(files)} changed file(s), none owned by another agent", file=out)
    return OK


def cmd_doctor(args: argparse.Namespace, out: TextIO) -> int:
    cfg = config.load(Path(args.directory))
    today = _today(args.today)
    statuses = sync.plan(cfg)
    log = cfg.path(cfg.handoff.file)
    st = handoff.status(log, cfg.handoff.max_age_days, today)
    pending = handoff.open_tasks(log)
    problems = sum(s.state is not sync.State.OK for s in statuses) + int(st.stale) + int(st.future > 0)
    if args.json:
        _emit_json(
            {
                "version": __version__,
                "root": str(cfg.root),
                "targets": _targets_json(statuses),
                "handoff": _status_json(st, cfg.handoff.file),
                "open_tasks": len(pending),
                "problems": problems,
                "healthy": not problems,
            },
            out,
        )
        return PROBLEM if problems else OK
    print(f"relaybaton {__version__} in {cfg.root}", file=out)
    print("instructions:", file=out)
    for status in statuses:
        label = "ok" if status.state is sync.State.OK else status.state.value.upper()
        print(f"  {label:<10}{status.path}", file=out)
    print("handoff log:", file=out)
    _print_status(st, cfg.handoff.file, out)
    if pending:
        oldest = pending[0]
        print(
            f"  info      {len(pending)} open task(s); oldest from {oldest.day.isoformat()}: {oldest.text}",
            file=out,
        )
    print("healthy" if not problems else f"{problems} problem(s) found", file=out)
    return PROBLEM if problems else OK


# ---------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="baton",
        description="Pass the baton between AI coding agents: shared instructions, "
        "an honest handoff log, and file ownership.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-C", dest="directory", default=".", help="run as if started in this directory")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    p = sub.add_parser("init", help="create baton.toml, AGENTS.md and HANDOFF.md")
    p.add_argument("--force", action="store_true", help="overwrite an existing baton.toml")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("sync", help="regenerate every agent's instruction file from the source")
    p.add_argument("--force", action="store_true", help="also replace hand-written target files")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("check", help="fail if any generated file is missing or out of date (for CI)")
    p.add_argument("--diff", action="store_true", help="show what differs")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("handoff", help="work with the handoff log")
    hsub = p.add_subparsers(dest="handoff_command", required=True, metavar="ACTION")

    h = hsub.add_parser("add", help="add an entry at the top of the log")
    h.add_argument("--author", required=True, help="who is handing off, e.g. claude")
    h.add_argument("--to", help="who should pick it up, e.g. codex")
    h.add_argument("--subject", help="a few words for the heading")
    h.add_argument("--date", type=_iso_date, help="entry date (default: today)")
    h.add_argument("message", nargs="*", help="the note; pass - to read it from stdin")
    h.set_defaults(func=cmd_handoff_add)

    h = hsub.add_parser("status", help="fail if the newest entry is too old")
    h.add_argument("--max-age", type=_positive_int, help="override handoff.max_age_days")
    h.add_argument("--today", type=_iso_date, help=argparse.SUPPRESS)
    h.add_argument("--json", action="store_true", help="machine-readable output")
    h.set_defaults(func=cmd_handoff_status)

    h = hsub.add_parser("open", help="list unchecked '- [ ]' tasks, oldest first")
    h.add_argument(
        "--max-age", type=_positive_int, help="fail if any open task is at least this many days old"
    )
    h.add_argument(
        "--for",
        dest="agent",
        type=_agent_name,
        metavar="AGENT",
        help="only tasks from entries addressed to AGENT ('→ AGENT') or mentioning @AGENT",
    )
    h.add_argument("--today", type=_iso_date, help=argparse.SUPPRESS)
    h.add_argument("--json", action="store_true", help="machine-readable output")
    h.set_defaults(func=cmd_handoff_open)

    h = hsub.add_parser("list", help="show the newest entries")
    h.add_argument("-n", type=_positive_int, default=5, help="how many (default 5)")
    h.set_defaults(func=cmd_handoff_list)

    p = sub.add_parser("guard", help="fail if an agent changed files another agent owns")
    p.add_argument("--agent", required=True, help="the agent whose changes are being checked")
    p.add_argument("--base", help="also include commits since this ref, e.g. origin/main")
    p.add_argument("files", nargs="*", help="check these paths instead of asking git")
    p.set_defaults(func=cmd_guard)

    p = sub.add_parser("doctor", help="run every check and summarize")
    p.add_argument("--today", type=_iso_date, help=argparse.SUPPRESS)
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None, out: TextIO | None = None) -> int:
    out = out or sys.stdout
    args = build_parser().parse_args(argv)
    try:
        return args.func(args, out)
    except config.ConfigError as exc:
        print(f"error: {exc}", file=out)
        return ERROR
