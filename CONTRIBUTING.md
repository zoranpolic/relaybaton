# Contributing

Thanks for helping. Issues and pull requests are welcome.

## Development setup

```bash
python3.11 -m venv .venv && . .venv/bin/activate
pip install -e . pytest==8.3.4 pytest-cov==6.0.0 ruff==0.8.6
```

## Before you open a pull request

```bash
ruff check . && ruff format --check .
python -m pytest --cov      # coverage must stay at or above 90%
baton check                 # this repository dogfoods relaybaton
```

## Ground rules

- No new runtime dependencies. The standard library is enough.
- Every behaviour change comes with a test.
- Edit `AGENTS.md`, never the generated `CLAUDE.md` / `GEMINI.md` /
  `.github/copilot-instructions.md`; then run `baton sync`.
- Add an entry to `CHANGELOG.md` under "Unreleased".
