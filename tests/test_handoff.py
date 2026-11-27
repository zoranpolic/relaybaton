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
