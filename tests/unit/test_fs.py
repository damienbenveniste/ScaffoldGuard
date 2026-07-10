"""Tests for filesystem safety helpers."""

from pathlib import Path

import pytest

from scaffold_guard.fs import (
    TransactionalWrite,
    apply_file_transaction,
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


def test_write_text_safely_writes_exact_utf8_bytes(tmp_path: Path) -> None:
    """Generated content is not changed by platform newline translation."""
    target = tmp_path / "policy.txt"
    content = "first\r\nsecond\n"

    write_text_safely(target, content, force=False)

    assert target.read_bytes() == content.encode("utf-8")


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


def test_apply_file_transaction_writes_all_files(tmp_path: Path) -> None:
    """A successful transaction atomically replaces and creates files."""
    (tmp_path / "existing.txt").write_text("old\n", encoding="utf-8")

    apply_file_transaction(
        tmp_path,
        (
            TransactionalWrite(Path("existing.txt"), "new\n"),
            TransactionalWrite(Path("nested/new.txt"), "created\n"),
        ),
    )

    assert (tmp_path / "existing.txt").read_text(encoding="utf-8") == "new\n"
    assert (tmp_path / "nested/new.txt").read_text(encoding="utf-8") == "created\n"


def test_apply_file_transaction_rolls_back_writes_and_backups(tmp_path: Path) -> None:
    """A failed post-write step restores all touched and derived files."""
    existing = tmp_path / "existing.txt"
    lockfile = tmp_path / "uv.lock"
    existing.write_text("old\n", encoding="utf-8")
    lockfile.write_text("old lock\n", encoding="utf-8")

    def fail_after_write() -> None:
        lockfile.write_text("new lock\n", encoding="utf-8")
        raise RuntimeError("verification failed")

    with pytest.raises(RuntimeError, match="verification failed"):
        apply_file_transaction(
            tmp_path,
            (
                TransactionalWrite(Path("existing.txt"), "new\n"),
                TransactionalWrite(Path("created.txt"), "created\n"),
            ),
            backup_paths=(Path("uv.lock"),),
            after_write=fail_after_write,
        )

    assert existing.read_text(encoding="utf-8") == "old\n"
    assert lockfile.read_text(encoding="utf-8") == "old lock\n"
    assert not (tmp_path / "created.txt").exists()


def test_apply_file_transaction_rejects_symlinked_target(tmp_path: Path) -> None:
    """Transactions preserve the existing symlink write boundary."""
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    (tmp_path / "link.txt").symlink_to(outside)

    with pytest.raises(FileExistsError, match="symbolic link"):
        apply_file_transaction(
            tmp_path,
            (TransactionalWrite(Path("link.txt"), "changed\n"),),
        )

    assert outside.read_text(encoding="utf-8") == "outside\n"


def test_apply_file_transaction_rejects_symlinked_parent(tmp_path: Path) -> None:
    """Transactions do not write through a symlink even when it resolves inside root."""
    real_directory = tmp_path / "real"
    real_directory.mkdir()
    (tmp_path / "linked").symlink_to(real_directory, target_is_directory=True)

    with pytest.raises(FileExistsError, match="symbolic link"):
        apply_file_transaction(
            tmp_path,
            (TransactionalWrite(Path("linked/new.txt"), "changed\n"),),
        )

    assert not (real_directory / "new.txt").exists()


@pytest.mark.parametrize("suffix", ["tmp", "rollback"])
def test_apply_file_transaction_preflights_reserved_scratch_paths(
    tmp_path: Path,
    suffix: str,
) -> None:
    """Scratch collisions fail before any transaction target is replaced."""
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("first old\n", encoding="utf-8")
    second.write_text("second old\n", encoding="utf-8")
    scratch = tmp_path / f".second.txt.scaffold-guard.{suffix}"
    scratch.write_text("reserved\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="temporary path already exists"):
        apply_file_transaction(
            tmp_path,
            (
                TransactionalWrite(Path("first.txt"), "first new\n"),
                TransactionalWrite(Path("second.txt"), "second new\n"),
            ),
        )

    assert first.read_text(encoding="utf-8") == "first old\n"
    assert second.read_text(encoding="utf-8") == "second old\n"
    assert scratch.read_text(encoding="utf-8") == "reserved\n"
