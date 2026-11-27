from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from relaybaton import handoff

D = date.fromisoformat


def test_add_creates_file_from_template(tmp_path: Path) -> None:
    log = tmp_path / "HANDOFF.md"
    entry = handoff.add_entry(log, "claude", "Tests pass; release is yours.", D("2026-11-27"), to="codex")
    text = log.read_text()
    assert text.startswith("# Handoff log")
    assert "### 2026-11-27 — claude → codex" in text
    assert entry.title == "claude → codex"


def test_newest_entry_goes_on_top(tmp_path: Path) -> None:
    log = tmp_path / "HANDOFF.md"
    handoff.add_entry(log, "codex", "first", D("2026-11-01"))
    handoff.add_entry(log, "claude", "second", D("2026-11-02"), subject="docs")
    entries = handoff.parse(log.read_text())
    assert [e.body for e in entries] == ["second", "first"]
    assert entries[0].title == "claude (docs)"


def test_add_to_file_without_log_heading_appends_section(tmp_path: Path) -> None:
    log = tmp_path / "NOTES.md"
    log.write_text("# Notes\n\nSome prose.\n")
    handoff.add_entry(log, "claude", "hello", D("2026-11-27"))
    text = log.read_text()
    assert text.index("Some prose.") < text.index(handoff.LOG_HEADING) < text.index("hello")


def test_content_after_log_is_preserved(tmp_path: Path) -> None:
    log = tmp_path / "HANDOFF.md"
    log.write_text(handoff.TEMPLATE + "\n### 2026-10-01 — old\n\nold body\n")
    handoff.add_entry(log, "claude", "new body", D("2026-11-27"))
    bodies = [e.body for e in handoff.parse(log.read_text())]
    assert bodies == ["new body", "old body"]


@pytest.mark.parametrize(("author", "message"), [("", "x"), ("claude", "   ")])
def test_rejects_empty_author_or_message(tmp_path: Path, author: str, message: str) -> None:
    with pytest.raises(ValueError):
        handoff.add_entry(tmp_path / "H.md", author, message, D("2026-11-27"))


def test_parse_ignores_bad_dates_and_stops_at_next_section() -> None:
    text = (
        "## Session log\n"
        "### 2026-13-45 — not a date\n"
        "### 2026-11-20: codex\n"
        "body line\n"
        "## Standing context\n"
        "not part of the entry\n"
    )
    entries = handoff.parse(text)
    assert len(entries) == 1
    assert entries[0].title == "codex"
    assert entries[0].body == "body line"


def test_status_missing_empty_fresh_and_stale(tmp_path: Path) -> None:
    log = tmp_path / "HANDOFF.md"
    st = handoff.status(log, 14, D("2026-11-27"))
    assert not st.exists and st.stale

    log.write_text(handoff.TEMPLATE)
    st = handoff.status(log, 14, D("2026-11-27"))
    assert st.exists and st.entries == 0 and st.stale

    handoff.add_entry(log, "claude", "x", D("2026-11-20"))
    st = handoff.status(log, 14, D("2026-11-27"))
    assert st.age_days == 7 and not st.stale

    st = handoff.status(log, 14, D("2026-12-04"))
    assert st.age_days == 14 and st.stale


def test_status_uses_newest_date_not_first_entry(tmp_path: Path) -> None:
    log = tmp_path / "HANDOFF.md"
    log.write_text("## Session log\n### 2026-06-14 — a\n\nold\n### 2026-11-25 — b\n\npasted out of order\n")
    st = handoff.status(log, 14, D("2026-11-27"))
    assert st.newest == D("2026-11-25") and st.age_days == 2


def test_fenced_examples_and_other_sections_are_not_entries() -> None:
    text = (
        "# Handoff log\n\n"
        "### 2099-01-01 — example before the log\n\n"
        "## Session log\n\n"
        "### 2026-11-20 — claude\n\nreal entry\n\n"
        "```markdown\n### 2099-01-01 — an example inside a fence\n```\n\n"
        "## Standing context\n\n"
        "### 2026-11-26 — a heading in another section\n"
    )
    entries = handoff.parse(text)
    assert [e.day for e in entries] == [D("2026-11-20")]
    assert "an example inside a fence" in entries[0].body


def test_future_dates_are_invalid_not_fresh(tmp_path: Path) -> None:
    log = tmp_path / "HANDOFF.md"
    log.write_text("## Session log\n### 2099-01-01 — typo\n\nx\n### 2026-09-01 — real\n\ny\n")
    st = handoff.status(log, 14, D("2026-11-27"))
    assert st.future == 1
    assert st.newest == D("2026-09-01") and st.stale and not st.healthy

    log.write_text("## Session log\n### 2099-01-01 — only a typo\n\nx\n")
    st = handoff.status(log, 14, D("2026-11-27"))
    assert st.newest is None and st.future == 1 and st.stale


def test_tasks_are_found_and_fenced_examples_skipped(tmp_path: Path) -> None:
    log = tmp_path / "HANDOFF.md"
    log.write_text(
        "## Session log\n"
        "### 2026-11-25 — claude → codex\n\n"
        "- [ ] cut the v0.2.0 release\n"
        "- [x] update the changelog\n"
        "```\n- [ ] an example, not a task\n```\n"
        "### 2026-11-20 — codex\n\n"
        "* [ ] review the Action inputs\n"
        "  + [X] nested and done\n"
    )
    all_tasks = handoff.tasks(handoff.parse(log.read_text()))
    assert [(t.text, t.done) for t in all_tasks] == [
        ("cut the v0.2.0 release", False),
        ("update the changelog", True),
        ("review the Action inputs", False),
        ("nested and done", True),
    ]
    pending = handoff.open_tasks(log)
    assert [t.text for t in pending] == ["review the Action inputs", "cut the v0.2.0 release"]
    assert pending[0].age(D("2026-11-27")) == 7


def test_open_tasks_missing_file(tmp_path: Path) -> None:
    assert handoff.open_tasks(tmp_path / "nope.md") == []


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("claude → codex", {"codex"}),
        ("claude → Codex (release)", {"codex"}),
        ("claude -> codex (typed by hand)", {"codex"}),
        ("claude → codex, gemini & copilot (fan-out)", {"codex", "gemini", "copilot"}),
        ("claude", set()),
        ("claude (rename a -> b)", set()),
        ("claude → codex (map a -> b)", {"codex"}),
        ("claude → (no recipient)", set()),
    ],
)
def test_recipients(title: str, expected: set[str]) -> None:
    assert handoff.recipients(title) == expected


@pytest.mark.parametrize(
    ("text", "agent", "expected"),
    [
        ("@codex please review", "codex", True),
        ("please review, @Codex.", "codex", True),
        ("hand to (@codex)", "codex", True),
        ("mail zoran@codex.dev", "codex", False),
        ("@codexbot owns this", "codex", False),
        ("@claude-code owns this", "claude-code", True),
        ("no mention at all", "codex", False),
    ],
)
def test_task_mentions(text: str, agent: str, expected: bool) -> None:
    task = handoff.Task(D("2026-11-27"), "claude", text, done=False)
    assert task.is_for(agent) is expected


def test_task_is_for_blank_agent() -> None:
    assert not handoff.Task(D("2026-11-27"), "claude → codex", "x", done=False).is_for("  ")


def test_open_tasks_for_agent(tmp_path: Path) -> None:
    log = tmp_path / "HANDOFF.md"
    log.write_text(
        "## Session log\n"
        "### 2026-11-26 — claude → codex (release)\n\n"
        "- [ ] cut the release\n"
        "- [x] already done\n"
        "### 2026-11-25 — codex\n\n"
        "- [ ] @claude rebase the branch\n"
        "- [ ] a note to self\n"
        "### 2026-11-20 — claude -> gemini, codex\n\n"
        "- [ ] check the docs\n"
    )
    assert [t.text for t in handoff.open_tasks(log, "codex")] == ["check the docs", "cut the release"]
    assert [t.text for t in handoff.open_tasks(log, "CLAUDE")] == ["@claude rebase the branch"]
    assert [t.text for t in handoff.open_tasks(log, "gemini")] == ["check the docs"]
    assert handoff.open_tasks(log, "copilot") == []
    assert len(handoff.open_tasks(log)) == 4
