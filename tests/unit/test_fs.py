"""Tests for filesystem safety helpers."""

from pathlib import Path

import pytest

from agent_safe.fs import (
    ensure_relative_safe_path,
    is_within_directory,
    list_created_files,
    write_text_safely,
)


def test_ensure_relative_safe_path_accepts_nested_relative_path() -> None:
    """Safe generated paths remain relative Path objects."""
    assert ensure_relative_safe_path("docs/index.md") == Path("docs/index.md")


@pytest.mark.parametrize(
    "unsafe_path",
    ["", ".", "../escape.md", "docs/../escape.md", str(Path.cwd() / "out.md")],
)
def test_ensure_relative_safe_path_rejects_unsafe_paths(unsafe_path: str) -> None:
    """Generated paths cannot be empty, absolute, or traversal-based."""
    with pytest.raises(ValueError, match="Generated file path"):
        ensure_relative_safe_path(unsafe_path)


def test_is_within_directory_detects_inside_and_outside_paths(tmp_path: Path) -> None:
    """Resolved candidate paths must stay below the target base."""
    base = tmp_path / "project"

    assert is_within_directory(base, base / "docs" / "index.md")
    assert not is_within_directory(base, tmp_path / "outside.md")


def test_write_text_safely_preserves_existing_files(tmp_path: Path) -> None:
    """Existing files are not overwritten unless the caller forces it."""
    target = tmp_path / "README.md"
    target.write_text("existing\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        write_text_safely(target, "new\n", force=False)

    assert target.read_text(encoding="utf-8") == "existing\n"


def test_write_text_safely_overwrites_when_forced(tmp_path: Path) -> None:
    """The explicit force flag permits overwriting an existing file."""
    target = tmp_path / "README.md"
    target.write_text("existing\n", encoding="utf-8")

    write_text_safely(target, "new\n", force=True)

    assert target.read_text(encoding="utf-8") == "new\n"


def test_write_text_safely_creates_parent_directories(tmp_path: Path) -> None:
    """Parent directories are created for safe generated files."""
    target = tmp_path / "docs" / "index.md"

    write_text_safely(target, "# Docs\n", force=False)

    assert target.read_text(encoding="utf-8") == "# Docs\n"


def test_write_text_safely_refuses_symlink_destinations(tmp_path: Path) -> None:
    """Generated writes must not follow symbolic links."""
    outside = tmp_path / "outside.md"
    outside.write_text("outside\n", encoding="utf-8")
    link = tmp_path / "link.md"
    link.symlink_to(outside)

    with pytest.raises(FileExistsError, match="symbolic link"):
        write_text_safely(link, "new\n", force=True)

    assert outside.read_text(encoding="utf-8") == "outside\n"


def test_list_created_files_returns_empty_list_for_missing_base(tmp_path: Path) -> None:
    """Missing output directories have no created files."""
    assert list_created_files(tmp_path / "missing") == []


def test_list_created_files_returns_sorted_relative_files(tmp_path: Path) -> None:
    """Created-file listing is stable and relative to the base directory."""
    write_text_safely(tmp_path / "b.txt", "b\n", force=False)
    write_text_safely(tmp_path / "nested" / "a.txt", "a\n", force=False)

    assert list_created_files(tmp_path) == [Path("b.txt"), Path("nested/a.txt")]
