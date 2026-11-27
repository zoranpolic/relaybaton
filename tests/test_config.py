from __future__ import annotations

from pathlib import Path

import pytest

from relaybaton import config
from relaybaton.config import ConfigError


def write(tmp_path: Path, text: str) -> None:
    (tmp_path / config.CONFIG_NAME).write_text(text, encoding="utf-8")


def test_template_loads_with_defaults(project: Path) -> None:
    cfg = config.load(project)
    assert cfg.source == "AGENTS.md"
    assert cfg.targets["claude"] == "CLAUDE.md"
    assert cfg.handoff.max_age_days == 14
    assert cfg.ownership["*-codex.*"] == "codex"


def test_found_from_subdirectory(project: Path) -> None:
    nested = project / "src" / "pkg"
    nested.mkdir(parents=True)
    assert config.load(nested).root == project.resolve()


def test_missing_config(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="no baton.toml"):
        config.load(tmp_path)


def test_empty_config_uses_defaults(tmp_path: Path) -> None:
    write(tmp_path, "")
    cfg = config.load(tmp_path)
    assert set(cfg.targets) == {"claude", "gemini", "copilot"}


@pytest.mark.parametrize("target", ["../outside.md", "/etc/passwd", "a/../../b.md"])
def test_rejects_paths_outside_root(tmp_path: Path, target: str) -> None:
    write(tmp_path, f'[targets]\nevil = "{target}"\n')
    with pytest.raises(ConfigError):
        config.load(tmp_path)


def test_rejects_target_overwriting_source(tmp_path: Path) -> None:
    write(tmp_path, '[targets]\nclaude = "AGENTS.md"\n')
    with pytest.raises(ConfigError, match="overwrite the source"):
        config.load(tmp_path)


@pytest.mark.parametrize(
    "text",
    [
        "source = 3",
        "targets = 1",
        "[targets]\nclaude = 1",
        "handoff = 1",
        "[handoff]\nmax_age_days = 0",
        "[handoff]\nmax_age_days = true",
        "[handoff]\nfile = 5",
        "this is not toml",
    ],
)
def test_invalid_values(tmp_path: Path, text: str) -> None:
    write(tmp_path, text)
    with pytest.raises(ConfigError):
        config.load(tmp_path)
