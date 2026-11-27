"""A dated, newest-first handoff log that agents (and people) append to.

Staleness is judged from the newest dated heading, never from the file's
modification time: sync clients and editors touch mtimes without adding a
single word, so an mtime check can report a dead channel as healthy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

LOG_HEADING = "## Session log"
HEADING_RE = re.compile(r"^###\s+(\d{4}-\d{2}-\d{2})\b\s*(?:[-—:]\s*)?(.*)$")

TEMPLATE = f"""\
# Handoff log

Shared notes between AI coding agents and the people working with them.
Newest entries first. Add one with `baton handoff add`.

{LOG_HEADING}
"""


@dataclass(frozen=True)
class Entry:
    day: date
    title: str
    body: str


@dataclass(frozen=True)
class HandoffStatus:
    exists: bool
    entries: int
    newest: date | None
    age_days: int | None
    max_age_days: int

    @property
    def stale(self) -> bool:
        return self.age_days is None or self.age_days >= self.max_age_days


def parse(text: str) -> list[Entry]:
    """Return every ``### YYYY-MM-DD`` entry in file order."""
    entries: list[Entry] = []
    current: tuple[date, str] | None = None
    body: list[str] = []

    def flush() -> None:
        if current is not None:
            entries.append(Entry(current[0], current[1], "\n".join(body).strip()))

    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match:
            try:
                day = date.fromisoformat(match.group(1))
            except ValueError:
                day = None
            if day is not None:
                flush()
                current, body = (day, match.group(2).strip()), []
                continue
        if line.startswith("## ") and current is not None:
            flush()
            current, body = None, []
            continue
        if current is not None:
            body.append(line)
    flush()
    return entries


def format_title(author: str, to: str | None, subject: str | None) -> str:
    title = author
    if to:
        title += f" → {to}"
    if subject:
        title += f" ({subject})"
    return title


def format_heading(day: date, title: str) -> str:
    return f"### {day.isoformat()} — {title}"


def add_entry(
    path: Path,
    author: str,
    message: str,
    day: date,
    to: str | None = None,
    subject: str | None = None,
) -> Entry:
    """Insert a new entry directly under the session-log heading."""
    if not author.strip():
        raise ValueError("author must not be empty")
    if not message.strip():
        raise ValueError("message must not be empty")
    text = path.read_text(encoding="utf-8") if path.exists() else TEMPLATE
    title = format_title(author.strip(), to, subject)
    block = f"{format_heading(day, title)}\n\n{message.strip()}\n"

    lines = text.splitlines()
    try:
        index = next(i for i, line in enumerate(lines) if line.strip() == LOG_HEADING)
    except StopIteration:
        new_text = text.rstrip("\n") + f"\n\n{LOG_HEADING}\n\n{block}"
    else:
        before = "\n".join(lines[: index + 1])
        after = "\n".join(lines[index + 1 :]).strip("\n")
        new_text = f"{before}\n\n{block}" + (f"\n{after}\n" if after else "")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")
    return Entry(day, title, message.strip())


def status(path: Path, max_age_days: int, today: date) -> HandoffStatus:
    if not path.exists():
        return HandoffStatus(False, 0, None, None, max_age_days)
    entries = parse(path.read_text(encoding="utf-8"))
    if not entries:
        return HandoffStatus(True, 0, None, None, max_age_days)
    # Use the newest date, not the first entry: people do paste entries out of order.
    newest = max(entry.day for entry in entries)
    return HandoffStatus(True, len(entries), newest, (today - newest).days, max_age_days)
