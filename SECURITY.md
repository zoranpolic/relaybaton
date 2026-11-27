# Security policy

## Supported versions

Only the latest release receives fixes.

## Reporting a vulnerability

Please use GitHub's **private vulnerability reporting** (Security tab, "Report a
vulnerability") rather than a public issue. You can expect an acknowledgement
within a week.

## Scope notes

- relaybaton has no runtime dependencies and never runs a shell.
- Every path from `baton.toml` is confined to the repository root; a report that
  breaks that guarantee is in scope.
