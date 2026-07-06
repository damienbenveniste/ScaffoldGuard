"""Filesystem helpers for safe scaffold writes."""

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
    path.write_text(content, encoding="utf-8")


def list_created_files(base: Path) -> list[Path]:
    """List files below `base` as sorted relative paths."""
    if not base.exists():
        return []
    return sorted(path.relative_to(base) for path in base.rglob("*") if path.is_file())
