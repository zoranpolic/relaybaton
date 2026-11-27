from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from relaybaton import config


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A project with the default template config and a small AGENTS.md."""
    (tmp_path / config.CONFIG_NAME).write_text(config.TEMPLATE, encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nRun `make test` before you push.\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def git_project(project: Path) -> Path:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=project, check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")
    git("add", ".")
    git("commit", "-q", "-m", "initial")
    return project
