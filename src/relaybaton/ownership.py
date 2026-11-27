"""Stop one agent from silently editing files another agent owns."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath


class GitError(Exception):
    """Git is missing or the repository state could not be read."""


@dataclass(frozen=True)
class Violation:
    path: str
    owner: str


def owner_of(path: str, rules: dict[str, str]) -> str | None:
    """Return the owner of ``path`` from the first matching glob, if any.

    A pattern without a slash matches the file name anywhere in the tree,
    like a .gitignore entry; a pattern with a slash matches the whole path.
    """
    posix = PurePosixPath(path.replace("\\", "/"))
    for pattern, owner in rules.items():
        target = str(posix) if "/" in pattern else posix.name
        if fnmatchcase(target, pattern):
            return owner
    return None


def check(files: list[str], agent: str, rules: dict[str, str]) -> list[Violation]:
    violations = []
    for path in sorted(set(files)):
        owner = owner_of(path, rules)
        if owner is not None and owner != agent:
            violations.append(Violation(path, owner))
    return violations


def _git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise GitError("git is not installed") from exc
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.decode("utf-8", "replace").strip()
        raise GitError(message or f"git {' '.join(args)} failed") from exc
    return result.stdout.decode("utf-8", "surrogateescape")


def _git_paths(root: Path, *args: str) -> list[str]:
    """Run a path-listing git command with ``-z`` and return the paths verbatim.

    Without ``-z`` git quotes and escapes unusual names (``"docs/caf\\303\\251.md"``),
    which would never match an ownership glob.
    """
    return [path for path in _git(root, *args, "-z").split("\0") if path]


def changed_files(root: Path, base: str | None = None) -> list[str]:
    """Files changed on this branch (since ``base``), staged, unstaged or untracked.

    Renames are reported as a deletion plus an addition (``--no-renames``), so
    moving an owned file to an unowned name still counts as touching it.
    """
    files: set[str] = set()
    try:
        _git(root, "rev-parse", "--verify", "--quiet", "HEAD")
        has_head = True
    except GitError:
        has_head = False  # brand-new repository with no commits yet
    diff = ("diff", "--name-only", "--no-renames")
    if base:
        if not has_head:
            raise GitError(f"cannot compare with {base!r}: the repository has no commits")
        files.update(_git_paths(root, *diff, f"{base}...HEAD"))
    if has_head:
        files.update(_git_paths(root, *diff, "HEAD"))
    files.update(_git_paths(root, *diff, "--cached"))
    files.update(_git_paths(root, "ls-files", "--others", "--exclude-standard"))
    return sorted(files)
