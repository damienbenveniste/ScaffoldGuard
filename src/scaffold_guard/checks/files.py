"""File discovery helpers for project checks."""

from collections.abc import Iterable
from pathlib import Path

TEXT_SUFFIXES = {".json", ".md", ".mdc", ".py", ".toml", ".ts", ".tsx", ".yaml", ".yml"}
IGNORED_DIRS = {
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
}


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
