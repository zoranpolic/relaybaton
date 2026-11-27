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
    future: int = 0  # entries dated after today: typos or examples, never evidence of freshness

    @property
    def stale(self) -> bool:
        return self.age_days is None or self.age_days >= self.max_age_days

    @property
    def healthy(self) -> bool:
        return not self.stale and self.future == 0


def _is_fence(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("```") or stripped.startswith("~~~")


def parse(text: str) -> list[Entry]:
    """Return the ``### YYYY-MM-DD`` entries of the session log, in file order.

    Only the ``## Session log`` section is read when the file has one, and
    headings inside fenced code blocks are ignored, so a documented example
    entry can never count as a real handoff.
    """
    lines = text.splitlines()
    has_log = any(line.strip() == LOG_HEADING for line in lines)
    if has_log:
        start = next(i for i, line in enumerate(lines) if line.strip() == LOG_HEADING) + 1
        lines = lines[start:]

    entries: list[Entry] = []
    current: tuple[date, str] | None = None
    body: list[str] = []
    in_fence = False

    def flush() -> None:
        if current is not None:
            entries.append(Entry(current[0], current[1], "\n".join(body).strip()))

    for line in lines:
        if _is_fence(line):
            in_fence = not in_fence
            if current is not None:
                body.append(line)
            continue
        if in_fence:
            if current is not None:
                body.append(line)
            continue
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
        if line.startswith("## "):
            flush()
            current, body = None, []
            if has_log:
                break  # the session log has ended
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


TASK_RE = re.compile(r"^\s*[-*+]\s+\[([ xX])\]\s+(.+?)\s*$")


@dataclass(frozen=True)
class Task:
    """A Markdown checkbox (``- [ ] ...``) inside a handoff entry."""

    day: date
    entry: str
    text: str
    done: bool

    def age(self, today: date) -> int:
        return (today - self.day).days

    def is_for(self, agent: str) -> bool:
        """True if the entry is addressed to ``agent`` or the task mentions ``@agent``."""
        wanted = agent.strip().lower()
        if not wanted:
            return False
        if wanted in recipients(self.entry):
            return True
        return any(name.lower() == wanted for name in MENTION_RE.findall(self.text))


# "author → codex (subject)": the recipients follow the arrow, up to the subject.
# "->" is accepted too, for entries typed by hand.
_RECIPIENTS_RE = re.compile(r"(?:→|->)\s*([^()]*?)\s*(?:\(.*)?$")
# "@codex" but not "zoran@codex.dev": no word character may precede the "@".
MENTION_RE = re.compile(r"(?<![\w@])@([A-Za-z0-9][\w-]*)")


def recipients(title: str) -> set[str]:
    """Lower-cased agent names an entry title addresses, e.g. ``{"codex"}``.

    Several recipients may be separated by commas or ``&``:
    ``claude → codex, gemini (release)``.
    """
    match = _RECIPIENTS_RE.search(title)
    if not match:
        return set()
    names = re.split(r"\s*[,&]\s*", match.group(1))
    return {name.strip().lower() for name in names if name.strip()}


def tasks(entries: list[Entry]) -> list[Task]:
    """Every checkbox in the given entries, skipping fenced examples."""
    found: list[Task] = []
    for entry in entries:
        in_fence = False
        for line in entry.body.splitlines():
            if _is_fence(line):
                in_fence = not in_fence
                continue
            match = None if in_fence else TASK_RE.match(line)
            if match:
                found.append(Task(entry.day, entry.title, match.group(2), match.group(1) != " "))
    return found


def open_tasks(path: Path, agent: str | None = None) -> list[Task]:
    """Unchecked tasks in the log, oldest first, so the longest-waiting work leads.

    With ``agent``, only tasks from entries addressed to that agent
    (``→ agent`` in the heading) or that mention ``@agent`` are returned.
    """
    if not path.exists():
        return []
    pending = [task for task in tasks(parse(path.read_text(encoding="utf-8"))) if not task.done]
    if agent is not None:
        pending = [task for task in pending if task.is_for(agent)]
    return sorted(pending, key=lambda task: task.day)


def status(path: Path, max_age_days: int, today: date) -> HandoffStatus:
    if not path.exists():
        return HandoffStatus(False, 0, None, None, max_age_days)
    entries = parse(path.read_text(encoding="utf-8"))
    future = sum(entry.day > today for entry in entries)
    dated = [entry.day for entry in entries if entry.day <= today]
    if not dated:
        return HandoffStatus(True, len(entries), None, None, max_age_days, future)
    # Use the newest date, not the first entry: people do paste entries out of order.
    newest = max(dated)
    return HandoffStatus(True, len(entries), newest, (today - newest).days, max_age_days, future)
