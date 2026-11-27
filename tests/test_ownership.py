from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from relaybaton import ownership

RULES = {"*-codex.*": "codex", "docs/legal/*": "human", "*-claude.*": "claude"}


@pytest.mark.parametrize(
    ("path", "owner"),
    [
        ("notes-codex.md", "codex"),
        ("deep/dir/plan-codex.json", "codex"),
        ("docs/legal/terms.md", "human"),
        ("other/docs/legal/terms.md", None),
        ("README.md", None),
        ("win\\style\\x-claude.md", "claude"),
    ],
)
def test_owner_of(path: str, owner: str | None) -> None:
    assert ownership.owner_of(path, RULES) == owner


def test_check_reports_only_other_agents_files() -> None:
    files = ["a-codex.md", "b-claude.md", "README.md", "a-codex.md"]
    assert ownership.check(files, "claude", RULES) == [ownership.Violation("a-codex.md", "codex")]
    assert ownership.check(files, "codex", RULES) == [ownership.Violation("b-claude.md", "claude")]


def test_changed_files_sees_modified_staged_and_untracked(git_project: Path) -> None:
    (git_project / "AGENTS.md").write_text("changed\n")
    (git_project / "staged-codex.md").write_text("x\n")
    subprocess.run(["git", "add", "staged-codex.md"], cwd=git_project, check=True)
    (git_project / "new.txt").write_text("x\n")
    assert ownership.changed_files(git_project) == ["AGENTS.md", "new.txt", "staged-codex.md"]


def test_changed_files_since_base(git_project: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=git_project, check=True, capture_output=True)

    git("checkout", "-q", "-b", "feature")
    (git_project / "plan-codex.md").write_text("x\n")
    git("add", ".")
    git("commit", "-q", "-m", "feature work")
    assert ownership.changed_files(git_project) == []
    assert ownership.changed_files(git_project, base="main") == ["plan-codex.md"]


def test_repository_without_commits(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "a.md").write_text("x\n")
    assert ownership.changed_files(tmp_path) == ["a.md"]
    with pytest.raises(ownership.GitError, match="no commits"):
        ownership.changed_files(tmp_path, base="main")


def test_not_a_repository(tmp_path: Path) -> None:
    with pytest.raises(ownership.GitError):
        ownership.changed_files(tmp_path)


def test_renaming_an_owned_file_still_counts(git_project: Path) -> None:
    """Regression: git's rename detection used to report only the new, unowned name."""

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=git_project, check=True, capture_output=True)

    (git_project / "plan-codex.md").write_text("owned\n" * 20)
    git("add", ".")
    git("commit", "-q", "-m", "owned file")
    git("checkout", "-q", "-b", "sneaky")
    git("mv", "plan-codex.md", "plan.md")
    git("commit", "-q", "-m", "rename away")
    files = ownership.changed_files(git_project, base="main")
    assert "plan-codex.md" in files
    assert ownership.check(files, "claude", RULES) == [ownership.Violation("plan-codex.md", "codex")]
