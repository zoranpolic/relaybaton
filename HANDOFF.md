# Handoff log

Shared notes between AI coding agents and the people working with them.
Newest entries first. Add one with `baton handoff add`.

## Session log

### 2026-11-27 — claude (v0.2.1)

Added `baton handoff open --for AGENT`: tasks from entries addressed to that agent or mentioning @AGENT.

### 2026-11-27 — claude (v0.2.0)

Added handoff open tasks, --json output and Cursor .mdc targets. 84 tests, 98% coverage.

- [x] add per-assignee filtering to handoff open
- [ ] publish to PyPI (needs a PyPI account and trusted publishing)

### 2026-11-27 — claude (v0.1.0)

First release: sync/check, handoff log, guard and doctor, with a composite GitHub Action and a pre-commit hook. 58 tests, 99% branch coverage. Next: handoff threads (resolve/open), Cursor and Windsurf targets, PyPI publishing.
