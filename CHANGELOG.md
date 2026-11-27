# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [0.2.1] - 2026-11-27

### Added
- `baton handoff open --for AGENT` lists only the tasks meant for one agent:
  those in entries addressed to it (`→ AGENT` in the heading, also `->` and
  comma-separated recipients) and those that mention `@AGENT`. Matching is
  case-insensitive, and e-mail addresses are not mentions. The JSON output
  gains a `for` field.

## [0.2.0] - 2026-11-27

### Added
- `baton handoff open`: lists unchecked `- [ ]` tasks from every handoff entry,
  oldest first, skipping fenced examples; `--max-age N` fails when a task has
  waited N days or more. `doctor` reports the open-task count.
- `--json` output for `check`, `doctor`, `handoff status` and `handoff open`,
  with the same exit codes as text mode.
- Cursor support: `.mdc` targets get Cursor's YAML front matter above the
  generated header; the generated marker is recognized below front matter.
- Commented Cursor and Windsurf examples in the `baton init` template; the
  pre-commit hook also watches `.mdc` and `.windsurfrules` targets.

## [0.1.2] - 2026-11-27

Fixes from an independent review by Codex.

### Fixed
- `baton guard` missed files whose names git quotes in plain output (non-ASCII,
  tabs, newlines, quotes); every path-listing git call now uses `-z`.
- Configurations where files collide (`handoff.file = "baton.toml"`, a target
  that is another agent's `AGENTS.<agent>.md` overlay, and similar) are rejected
  before anything is written.
- The handoff log is read only inside `## Session log`; headings in code fences
  or other sections no longer count, and future-dated entries are reported as
  invalid instead of making the log look fresh.

### Changed
- README describes `guard` as reporting violations after the fact and the
  dependency story precisely; the Action documents how its input is split.
- CI exercises the Action with multi-word commands and shell metacharacters.

## [0.1.1] - 2026-11-27

### Fixed
- `baton guard` could be bypassed by renaming an owned file: git's rename
  detection reported only the new, unowned name. Renames now count as a
  deletion of the original plus an addition.
- Two agents configured with the same target file, or a target that would
  overwrite the handoff log, were silently accepted; both are now config errors.
- Agent names that form a path (used for `AGENTS.<agent>.md` overlays) are
  confined to the repository like every other path.
- `--max-age` and `handoff list -n` now reject zero and negative values.

### Changed
- `baton guard --base` explains how to fetch full history when the comparison
  fails in a shallow clone.

## [0.1.0] - 2026-11-27

### Added
- `baton init`: creates `baton.toml`, `AGENTS.md` and `HANDOFF.md`.
- `baton sync` / `baton check`: generate per-agent instruction files from one
  source, with per-agent overlays (`AGENTS.<agent>.md`), drift detection and diffs.
  Hand-written files are never overwritten without `--force`.
- `baton handoff add | list | status`: a dated, newest-first handoff log whose
  freshness is judged from entry dates, not file modification times.
- `baton guard`: fails when an agent changed files owned by another agent.
- `baton doctor`: runs every check and summarizes.
- Composite GitHub Action and pre-commit hook.
