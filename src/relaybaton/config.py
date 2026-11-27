"""Load and validate ``baton.toml``."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_NAME = "baton.toml"

DEFAULT_TARGETS: dict[str, str] = {
    "claude": "CLAUDE.md",
    "gemini": "GEMINI.md",
    "copilot": ".github/copilot-instructions.md",
}


class ConfigError(Exception):
    """The configuration is missing or invalid."""


@dataclass(frozen=True)
class HandoffConfig:
    file: str = "HANDOFF.md"
    max_age_days: int = 14


@dataclass(frozen=True)
class Config:
    root: Path
    source: str = "AGENTS.md"
    targets: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_TARGETS))
    handoff: HandoffConfig = field(default_factory=HandoffConfig)
    ownership: dict[str, str] = field(default_factory=dict)

    def path(self, relative: str) -> Path:
        """Resolve a config-relative path, refusing anything outside the root."""
        return safe_path(self.root, relative)


def safe_path(root: Path, relative: str) -> Path:
    """Join ``relative`` onto ``root`` and make sure it stays inside ``root``.

    Config files are often copied between repositories, so a target such as
    ``../../.bashrc`` must never be written.
    """
    if not relative or Path(relative).is_absolute():
        raise ConfigError(f"path must be relative to the project root: {relative!r}")
    resolved_root = root.resolve()
    candidate = (resolved_root / relative).resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise ConfigError(f"path escapes the project root: {relative!r}")
    return candidate


def find_root(start: Path) -> Path:
    """Walk up from ``start`` to the first directory containing ``baton.toml``."""
    current = start.resolve()
    for directory in (current, *current.parents):
        if (directory / CONFIG_NAME).is_file():
            return directory
    raise ConfigError(f"no {CONFIG_NAME} found in {current} or any parent (run `baton init`)")


def _require_str_table(value: object, name: str) -> dict[str, str]:
    if not isinstance(value, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    ):
        raise ConfigError(f"[{name}] must be a table of strings")
    return dict(value)


def load(start: Path) -> Config:
    """Find and parse ``baton.toml`` at or above ``start``."""
    root = find_root(start)
    try:
        data = tomllib.loads((root / CONFIG_NAME).read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{CONFIG_NAME}: {exc}") from exc

    source = data.get("source", "AGENTS.md")
    if not isinstance(source, str):
        raise ConfigError("source must be a string")

    targets = _require_str_table(data.get("targets", DEFAULT_TARGETS), "targets")
    ownership = _require_str_table(data.get("ownership", {}), "ownership")

    handoff_data = data.get("handoff", {})
    if not isinstance(handoff_data, dict):
        raise ConfigError("[handoff] must be a table")
    handoff_file = handoff_data.get("file", "HANDOFF.md")
    max_age = handoff_data.get("max_age_days", 14)
    if not isinstance(handoff_file, str):
        raise ConfigError("handoff.file must be a string")
    if not isinstance(max_age, int) or isinstance(max_age, bool) or max_age < 1:
        raise ConfigError("handoff.max_age_days must be a positive integer")

    config = Config(
        root=root,
        source=source,
        targets=targets,
        handoff=HandoffConfig(file=handoff_file, max_age_days=max_age),
        ownership=ownership,
    )
    # Validate every path up front so a bad config fails before anything is written.
    # Every file relaybaton reads or writes must be distinct, or one command would
    # corrupt another's input (e.g. `handoff add` rewriting baton.toml).
    roles: dict[Path, str] = {(root / CONFIG_NAME).resolve(): CONFIG_NAME}

    def claim(path: Path, role: str) -> None:
        if path in roles:
            raise ConfigError(f"{role} would overwrite {roles[path]}")
        roles[path] = role

    claim(config.path(config.source), f"source {config.source!r}")
    for agent in config.targets:
        # An agent name must not smuggle in a path, and its overlay is an input.
        claim(config.path(f"AGENTS.{agent}.md"), f"overlay for {agent!r}")
    claim(config.path(config.handoff.file), f"handoff log {config.handoff.file!r}")
    for agent, target in config.targets.items():
        claim(config.path(target), f"target for {agent!r}")
    return config


TEMPLATE = """\
# relaybaton configuration. See https://github.com/zoranpolic/relaybaton

# The one file you edit. Every target below is generated from it.
source = "AGENTS.md"

# Agent name -> generated instruction file.
# Add AGENTS.<agent>.md next to the source for agent-specific extras.
[targets]
claude = "CLAUDE.md"
gemini = "GEMINI.md"
copilot = ".github/copilot-instructions.md"

[handoff]
file = "HANDOFF.md"
# `baton handoff status` fails when the newest entry is this many days old.
max_age_days = 14

# Glob -> owning agent. `baton guard --agent X` fails if X changed a file
# owned by someone else.
[ownership]
"*-codex.*" = "codex"
"*-claude.*" = "claude"
"""
