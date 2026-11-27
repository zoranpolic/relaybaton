from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

import pytest

from relaybaton import __version__
from relaybaton.cli import ERROR, OK, PROBLEM, main


def run(project: Path, *args: str) -> tuple[int, str]:
    out = io.StringIO()
    code = main(["-C", str(project), *args], out=out)
    return code, out.getvalue()


def test_init_then_sync_then_check(tmp_path: Path) -> None:
    code, out = run(tmp_path, "init")
    assert code == OK and "created baton.toml" in out and "created HANDOFF.md" in out
    assert run(tmp_path, "init")[0] == ERROR
    assert run(tmp_path, "init", "--force")[0] == OK

    assert run(tmp_path, "check")[0] == PROBLEM
    code, out = run(tmp_path, "sync")
    assert code == OK and "wrote" in out
    code, out = run(tmp_path, "check")
    assert code == OK and "all 3 target(s) match AGENTS.md" in out


def test_check_diff_and_sync_skips_hand_written(project: Path) -> None:
    (project / "CLAUDE.md").write_text("hand written\n")
    code, out = run(project, "check", "--diff")
    assert code == PROBLEM and "UNMANAGED" in out and "(file is missing)" in out
    code, out = run(project, "sync")
    assert code == PROBLEM and "skipped" in out
    assert run(project, "sync", "--force")[0] == OK


def test_handoff_add_list_status(project: Path) -> None:
    code, out = run(
        project,
        "handoff",
        "add",
        "--author",
        "claude",
        "--to",
        "codex",
        "--date",
        "2026-11-20",
        "Docs",
        "are",
        "done",
    )
    assert code == OK and "claude → codex" in out
    code, out = run(project, "handoff", "list")
    assert code == OK and "2026-11-20  claude → codex" in out and "Docs are done" in out
    assert run(project, "handoff", "status", "--today", "2026-11-27")[0] == OK
    code, out = run(project, "handoff", "status", "--today", "2026-12-20")
    assert code == PROBLEM and "STALE" in out
    assert run(project, "handoff", "status", "--today", "2026-12-20", "--max-age", "60")[0] == OK


def test_handoff_reads_stdin(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("from a pipe\n"))
    assert run(project, "handoff", "add", "--author", "ci", "-")[0] == OK
    assert "from a pipe" in (project / "HANDOFF.md").read_text()


def test_handoff_empty_message_is_an_error(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert run(project, "handoff", "add", "--author", "ci", "-")[0] == ERROR


def test_handoff_missing_file(project: Path) -> None:
    code, out = run(project, "handoff", "status")
    assert code == PROBLEM and "MISSING" in out
    assert run(project, "handoff", "list")[0] == PROBLEM


def test_handoff_without_dated_entries(project: Path) -> None:
    (project / "HANDOFF.md").write_text("# Handoff log\n\n## Session log\n")
    code, out = run(project, "handoff", "status")
    assert code == PROBLEM and "no dated entries" in out


def test_guard(git_project: Path) -> None:
    (git_project / "plan-codex.md").write_text("x\n")
    code, out = run(git_project, "guard", "--agent", "claude")
    assert code == PROBLEM and "plan-codex.md is owned by codex" in out
    assert run(git_project, "guard", "--agent", "codex")[0] == OK
    assert run(git_project, "guard", "--agent", "claude", "README.md")[0] == OK


def test_guard_outside_git_and_without_rules(project: Path) -> None:
    assert run(project, "guard", "--agent", "claude")[0] == ERROR
    (project / "baton.toml").write_text("")
    code, out = run(project, "guard", "--agent", "claude")
    assert code == OK and "nothing to guard" in out


def test_doctor(project: Path) -> None:
    code, out = run(project, "doctor", "--today", "2026-11-27")
    assert code == PROBLEM and "4 problem(s)" in out
    run(project, "sync")
    run(project, "handoff", "add", "--author", "claude", "--date", "2026-11-27", "hi")
    code, out = run(project, "doctor", "--today", "2026-11-27")
    assert code == OK and out.strip().endswith("healthy")


def test_config_error_is_reported(tmp_path: Path) -> None:
    code, out = run(tmp_path, "check")
    assert code == ERROR and "no baton.toml" in out


def test_bad_date_is_rejected(project: Path) -> None:
    with pytest.raises(SystemExit):
        main(["-C", str(project), "handoff", "add", "--author", "a", "--date", "11/27/2026", "x"])


def test_module_entry_point(project: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "relaybaton", "--version"], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == f"baton {__version__}"
