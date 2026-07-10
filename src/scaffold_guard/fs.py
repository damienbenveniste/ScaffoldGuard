"""Filesystem helpers for safe scaffold writes."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path


def ensure_relative_safe_path(path: str) -> Path:
    """Return a relative path after rejecting absolute or escaping paths."""
    candidate = Path(path)
    if path == "" or candidate == Path():
        msg = "Generated file path must not be empty."
        raise ValueError(msg)
    if candidate.is_absolute():
        msg = f"Generated file path must be relative: {path}"
        raise ValueError(msg)
    if ".." in candidate.parts:
        msg = f"Generated file path must not contain '..': {path}"
        raise ValueError(msg)
    return candidate


def is_within_directory(base: Path, candidate: Path) -> bool:
    """Return whether `candidate` resolves inside `base`."""
    resolved_base = base.resolve(strict=False)
    resolved_candidate = candidate.resolve(strict=False)
    try:
        resolved_candidate.relative_to(resolved_base)
    except ValueError:
        return False
    return True


def write_text_safely(path: Path, content: str, *, force: bool) -> None:
    """Write UTF-8 text while preserving existing files unless forced."""
    if path.exists() and not force:
        msg = f"Refusing to overwrite existing file: {path}"
        raise FileExistsError(msg)
    if path.is_symlink():
        msg = f"Refusing to write through symbolic link: {path}"
        raise FileExistsError(msg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))


def list_created_files(base: Path) -> list[Path]:
    """List files below `base` as sorted relative paths."""
    if not base.exists():
        return []
    return sorted(path.relative_to(base) for path in base.rglob("*") if path.is_file())


def apply_file_transaction(
    root: Path,
    writes: Iterable[TransactionalWrite],
    *,
    backup_paths: Iterable[Path] = (),
    after_write: Callable[[], None] | None = None,
) -> None:
    """Apply validated text writes atomically per file and roll back on failure."""
    resolved_root = root.resolve(strict=False)
    write_list = tuple(writes)
    backup_list = tuple(backup_paths)
    relative_paths = tuple(write.path for write in write_list) + backup_list
    if len(set(relative_paths)) != len(relative_paths):
        raise ValueError("Transactional paths must be unique.")

    targets = tuple(_transaction_target(resolved_root, path) for path in relative_paths)
    write_targets = targets[: len(write_list)]
    write_temporaries = tuple(
        target.with_name(f".{target.name}.scaffold-guard.tmp") for target in write_targets
    )
    rollback_temporaries = {
        target: target.with_name(f".{target.name}.scaffold-guard.rollback") for target in targets
    }
    scratch_paths = (*write_temporaries, *rollback_temporaries.values())
    if len({*targets, *scratch_paths}) != len(targets) + len(scratch_paths):
        raise ValueError("Transactional paths conflict with reserved scratch paths.")
    for scratch_path in scratch_paths:
        _require_available_temporary_path(scratch_path)

    snapshots = {target: _snapshot_file(target) for target in targets}
    try:
        for write, target, temporary_path in zip(
            write_list,
            write_targets,
            write_temporaries,
            strict=True,
        ):
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary_path.write_bytes(write.content.encode("utf-8"))
            previous_mode = snapshots[target].mode
            if previous_mode is not None:
                temporary_path.chmod(previous_mode)
            temporary_path.replace(target)
        if after_write is not None:
            after_write()
    except Exception:
        _restore_snapshots(snapshots, rollback_temporaries)
        raise
    finally:
        for temporary_path in scratch_paths:
            temporary_path.unlink(missing_ok=True)


def _transaction_target(root: Path, relative_path: Path) -> Path:
    """Resolve and validate one transaction path below the project root."""
    safe_path = ensure_relative_safe_path(relative_path.as_posix())
    target = root / safe_path
    if _has_symlink_component(root, safe_path):
        msg = f"Refusing transactional write through symbolic link: {relative_path}"
        raise FileExistsError(msg)
    if not is_within_directory(root, target):
        msg = f"Refusing transactional write outside project root: {relative_path}"
        raise ValueError(msg)
    return target


def has_symlink_component(root: Path, relative_path: Path) -> bool:
    """Return whether an existing destination component is a symbolic link."""
    candidate = root
    for part in relative_path.parts:
        candidate /= part
        if candidate.is_symlink():
            return True
    return False


def _has_symlink_component(root: Path, relative_path: Path) -> bool:
    """Return whether an existing destination component is a symbolic link."""
    return has_symlink_component(root, relative_path)


def _snapshot_file(path: Path) -> _FileSnapshot:
    """Capture one file before a transaction mutates it."""
    if not path.exists():
        return _FileSnapshot(content=None, mode=None)
    if not path.is_file():
        msg = f"Transactional path is not a regular file: {path}"
        raise FileExistsError(msg)
    return _FileSnapshot(content=path.read_bytes(), mode=path.stat().st_mode)


def _require_available_temporary_path(path: Path) -> None:
    """Reject a pre-existing transaction scratch path."""
    if path.exists() or path.is_symlink():
        msg = f"Transactional temporary path already exists: {path}"
        raise FileExistsError(msg)


def _restore_snapshots(
    snapshots: dict[Path, _FileSnapshot],
    rollback_paths: dict[Path, Path],
) -> None:
    """Restore all transaction paths after an apply failure."""
    for path, snapshot in snapshots.items():
        if snapshot.content is None:
            path.unlink(missing_ok=True)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = rollback_paths[path]
        temporary_path.write_bytes(snapshot.content)
        if snapshot.mode is not None:
            temporary_path.chmod(snapshot.mode)
        temporary_path.replace(path)


@dataclass(frozen=True, slots=True)
class TransactionalWrite:
    """One relative UTF-8 file write in a rollback-capable transaction."""

    path: Path
    content: str


@dataclass(frozen=True, slots=True)
class _FileSnapshot:
    """Original file bytes and mode used when rolling back."""

    content: bytes | None
    mode: int | None
