"""File discovery helpers for project checks."""

import shutil
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

TEXT_SUFFIXES: frozenset[str] = frozenset(
    (".json", ".md", ".mdc", ".py", ".toml", ".ts", ".tsx", ".yaml", ".yml")
)
IGNORED_DIRS: frozenset[str] = frozenset(
    (
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "htmlcov",
        "node_modules",
        "site",
    )
)


@dataclass(frozen=True, slots=True)
class GitPathState:
    """Git tracking and ignore status for one repository-relative path."""

    tracked: bool
    ignored: bool
    reliable: bool


def relative_to_root(root: Path, path: Path) -> Path:
    """Return `path` relative to `root`."""
    return path.relative_to(root)


def iter_text_files(root: Path, paths: Iterable[Path]) -> Iterable[Path]:
    """Yield readable text files below the requested relative paths."""
    for relative_path in paths:
        candidate = root / relative_path
        if candidate.is_file() and candidate.suffix in TEXT_SUFFIXES:
            yield candidate
        elif candidate.is_dir():
            yield from _iter_text_files_in_tree(candidate)


def _iter_text_files_in_tree(directory: Path) -> Iterable[Path]:
    """Yield text files below a directory while skipping runtime artifacts."""
    for path in directory.rglob("*"):
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            yield path


def read_lines(path: Path) -> list[str]:
    """Read UTF-8 text lines, replacing malformed bytes for scan stability."""
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def gitignore_entries(root: Path) -> set[str]:
    """Return simple path entries from `.gitignore`."""
    gitignore_path = root / ".gitignore"
    if not gitignore_path.exists():
        return set()
    entries: set[str] = set()
    for line in gitignore_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            entries.add(stripped.rstrip("/"))
    return entries


def git_path_state(root: Path, relative_path: Path) -> GitPathState:
    """Return Git tracking and ignore state without reading the target file."""
    _validate_relative_path(relative_path)
    git_path = shutil.which("git")
    if git_path is None:
        return _state_without_git(root, relative_path)

    worktree = _run_git(
        git_path,
        root,
        ("rev-parse", "--is-inside-work-tree"),
    )
    if worktree is None:
        return _state_without_git(root, relative_path)
    if worktree.returncode != 0:
        return _state_without_worktree(root, relative_path)
    return _state_in_worktree(root, relative_path, git_path, worktree.stdout.strip())


def _state_in_worktree(
    root: Path,
    relative_path: Path,
    git_path: str,
    inside_worktree: str,
) -> GitPathState:
    """Inspect one path after Git has identified the worktree state."""
    if inside_worktree == "false":
        return _state_outside_repository(root, relative_path)
    if inside_worktree != "true":
        return GitPathState(tracked=False, ignored=False, reliable=False)

    path_argument = relative_path.as_posix()
    tracked = _run_git(
        git_path,
        root,
        ("ls-files", "--error-unmatch", "--", path_argument),
    )
    ignored = _run_git(
        git_path,
        root,
        ("check-ignore", "--no-index", "--quiet", "--", path_argument),
    )
    if tracked is None or ignored is None:
        return GitPathState(tracked=False, ignored=False, reliable=False)
    if tracked.returncode not in {0, 1} or ignored.returncode not in {0, 1}:
        return GitPathState(tracked=False, ignored=False, reliable=False)
    return GitPathState(
        tracked=tracked.returncode == 0,
        ignored=ignored.returncode == 0,
        reliable=True,
    )


def _validate_relative_path(relative_path: Path) -> None:
    """Reject paths that could escape or ambiguously name the repository root."""
    if relative_path.is_absolute() or not relative_path.parts or ".." in relative_path.parts:
        msg = "Git path must be a non-empty repository-relative path without '..'."
        raise ValueError(msg)


def _run_git(
    git_path: str,
    root: Path,
    arguments: tuple[str, ...],
) -> subprocess.CompletedProcess[str] | None:
    """Run one read-only Git query and return `None` on execution failure."""
    run = subprocess.run
    try:
        return run(
            (git_path, "-C", str(root), *arguments),
            check=False,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _state_without_git(root: Path, relative_path: Path) -> GitPathState:
    """Use repository metadata to distinguish no Git from unavailable Git state."""
    if _has_git_metadata(root):
        return GitPathState(tracked=False, ignored=False, reliable=False)
    return _state_outside_repository(root, relative_path)


def _state_without_worktree(root: Path, relative_path: Path) -> GitPathState:
    """Fail closed when Git metadata exists but worktree detection failed."""
    if _has_git_metadata(root):
        return GitPathState(tracked=False, ignored=False, reliable=False)
    return _state_outside_repository(root, relative_path)


def _state_outside_repository(root: Path, relative_path: Path) -> GitPathState:
    """Return the explicit root `.gitignore` state when no repository exists."""
    return GitPathState(
        tracked=False,
        ignored=_explicitly_ignored_without_repository(root, relative_path),
        reliable=True,
    )


def _explicitly_ignored_without_repository(root: Path, relative_path: Path) -> bool:
    """Evaluate ordered exact-path rules without interpreting broader patterns."""
    gitignore_path = root / ".gitignore"
    if not gitignore_path.is_file():
        return False

    relative = relative_path.as_posix()
    ignored = False
    for line in gitignore_path.read_text(encoding="utf-8").splitlines():
        rule = line.strip()
        if not rule or rule.startswith("#"):
            continue
        negated = rule.startswith("!")
        pattern = rule[1:] if negated else rule
        if pattern in {relative, f"/{relative}"}:
            ignored = not negated
    return ignored


def _has_git_metadata(root: Path) -> bool:
    """Return whether the root or an ancestor has a Git directory or worktree file."""
    return any((candidate / ".git").exists() for candidate in (root, *root.parents))
