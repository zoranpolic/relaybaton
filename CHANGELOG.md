# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

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
