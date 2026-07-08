"""Audited git publishing for generated projects."""

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path

from scaffold_guard.project_config import GeneratedProjectConfig, load_generated_project_config
from scaffold_guard.validation import ValidationReport, run_validation


class PublishError(ValueError):
    """Raised when a generated project cannot be safely published."""


@dataclass(frozen=True, slots=True)
class GitStatus:
    """Relevant dirty git paths grouped by index state."""

    staged: frozenset[Path]
    unstaged: frozenset[Path]
    untracked: frozenset[Path]

    @property
    def dirty(self) -> frozenset[Path]:
        """Return every changed path reported by git."""
        return self.staged | self.unstaged | self.untracked

    @property
    def has_unstaged_scope(self) -> bool:
        """Return whether changes exist outside the current index."""
        return bool(self.unstaged or self.untracked)


@dataclass(frozen=True, slots=True)
class GitCommandResult:
    """Captured output from one git command."""

    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True, slots=True)
class PublishSummary:
    """Summary of an audited publish operation."""

    root: Path
    remote: str
    branch: str
    commit_created: bool
    validation: ValidationReport


def publish_changes(
    path: Path,
    *,
    message: str | None,
    all_changes: bool,
    files: tuple[Path, ...],
    remote: str | None,
    branch: str | None,
    quick: bool,
    push_only: bool,
) -> PublishSummary:
    """Validate, commit, and push a generated project through a narrow path."""
    config = load_generated_project_config(path)
    root = _git_root(config)
    if root != config.root:
        msg = (
            "Refusing to publish from a nested generated project. Run from the git root "
            f"or move scaffold-guard.toml to the repository root: {root}"
        )
        raise PublishError(msg)

    commit_message = _normalize_commit_message(message, push_only=push_only)
    target_remote, target_branch = _target_remote_branch(
        root,
        remote=remote,
        branch=branch,
    )
    validation = _run_publish_validation(config, quick=quick)
    status = _git_status(root)
    selected_files = _normalize_selected_files(files)

    if push_only:
        _ensure_push_only_status(status)
        _run_git(("push", target_remote, f"HEAD:{target_branch}"), cwd=root)
        return PublishSummary(
            root=root,
            remote=target_remote,
            branch=target_branch,
            commit_created=False,
            validation=validation,
        )

    _ensure_publishable_status(status, all_changes=all_changes, selected_files=selected_files)
    if status.has_unstaged_scope:
        _stage_publish_scope(root, all_changes=all_changes, selected_files=selected_files)

    staged_status = _git_status(root)
    _ensure_staged_scope(staged_status)
    _run_git(("commit", "-m", commit_message), cwd=root)
    _run_git(("push", target_remote, f"HEAD:{target_branch}"), cwd=root)
    return PublishSummary(
        root=root,
        remote=target_remote,
        branch=target_branch,
        commit_created=True,
        validation=validation,
    )


def _git_root(config: GeneratedProjectConfig) -> Path:
    """Return the git root for a generated project."""
    root_text = _git_capture(("rev-parse", "--show-toplevel"), cwd=config.root)
    return Path(root_text).resolve(strict=False)


def _normalize_commit_message(message: str | None, *, push_only: bool) -> str:
    """Return a non-empty commit message unless the operation is push-only."""
    if message is None:
        if push_only:
            return ""
        msg = "A commit message is required unless --push-only is used."
        raise PublishError(msg)
    normalized = message.strip()
    if normalized:
        return normalized
    if push_only:
        return ""
    msg = "Commit message cannot be empty."
    raise PublishError(msg)


def _target_remote_branch(root: Path, *, remote: str | None, branch: str | None) -> tuple[str, str]:
    """Return the remote and branch to push to."""
    upstream_remote: str | None = None
    upstream_branch: str | None = None
    if remote is None or branch is None:
        upstream_remote, upstream_branch = _split_upstream(_optional_upstream(root))
    target_remote = remote or upstream_remote or "origin"
    target_branch = branch or upstream_branch or _current_branch(root)
    _validate_git_ref_part(target_remote, label="remote")
    _validate_git_ref_part(target_branch, label="branch")
    return target_remote, target_branch


def _optional_upstream(root: Path) -> str | None:
    """Return the configured upstream ref when one exists."""
    try:
        return _git_capture(
            ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"),
            cwd=root,
        )
    except PublishError:
        return None


def _split_upstream(upstream: str | None) -> tuple[str | None, str | None]:
    """Split an upstream ref such as `origin/main` into remote and branch."""
    if upstream is None or "/" not in upstream:
        return None, None
    remote, branch = upstream.split("/", maxsplit=1)
    return remote, branch


def _current_branch(root: Path) -> str:
    """Return the current branch, refusing detached HEAD."""
    branch = _git_capture(("branch", "--show-current"), cwd=root)
    if branch:
        return branch
    msg = "Refusing to publish from detached HEAD."
    raise PublishError(msg)


def _validate_git_ref_part(value: str, *, label: str) -> None:
    """Reject empty or option-like remote and branch arguments."""
    if not value.strip():
        msg = f"Git {label} cannot be empty."
        raise PublishError(msg)
    if value.startswith("-"):
        msg = f"Git {label} cannot start with '-': {value}"
        raise PublishError(msg)


def _run_publish_validation(config: GeneratedProjectConfig, *, quick: bool) -> ValidationReport:
    """Run the generated project's validation gate before publishing."""
    report = run_validation(config.root, quick=quick, capture=False)
    if report.ok:
        return report
    failed = next(command for command in report.commands if not command.ok)
    msg = f"Validation failed before publish: {failed.command_text}"
    raise PublishError(msg)


def _normalize_selected_files(files: tuple[Path, ...]) -> frozenset[Path]:
    """Return normalized relative file paths selected for publishing."""
    selected: set[Path] = set()
    for file_path in files:
        if file_path.is_absolute():
            msg = f"Publish file paths must be relative: {file_path}"
            raise PublishError(msg)
        normalized = Path(file_path.as_posix())
        if normalized.as_posix() in {"", "."} or ".." in normalized.parts:
            msg = f"Publish file path must stay inside the project: {file_path}"
            raise PublishError(msg)
        selected.add(normalized)
    return frozenset(selected)


def _ensure_push_only_status(status: GitStatus) -> None:
    """Refuse push-only when the working tree is dirty."""
    if status.dirty:
        msg = "Refusing --push-only with uncommitted changes."
        raise PublishError(msg)


def _ensure_publishable_status(
    status: GitStatus,
    *,
    all_changes: bool,
    selected_files: frozenset[Path],
) -> None:
    """Validate that the dirty scope is explicit and not mixed."""
    if not status.dirty:
        msg = "No changes to commit. Use --push-only to push existing commits."
        raise PublishError(msg)
    if status.staged and status.has_unstaged_scope:
        msg = "Refusing mixed staged and unstaged changes. Publish one reviewed scope at a time."
        raise PublishError(msg)
    if all_changes and selected_files:
        msg = "Use either --all or --file, not both."
        raise PublishError(msg)
    if status.has_unstaged_scope and not all_changes and not selected_files:
        msg = "Unstaged changes require an explicit --all or --file selection."
        raise PublishError(msg)
    if selected_files and selected_files != status.dirty:
        unselected = sorted(path.as_posix() for path in status.dirty - selected_files)
        if unselected:
            msg = "Refusing unreviewed dirty files outside --file selection: " + ", ".join(
                unselected
            )
            raise PublishError(msg)
        missing = sorted(path.as_posix() for path in selected_files - status.dirty)
        if missing:
            msg = "Selected files are not dirty: " + ", ".join(missing)
            raise PublishError(msg)


def _stage_publish_scope(
    root: Path,
    *,
    all_changes: bool,
    selected_files: frozenset[Path],
) -> None:
    """Stage the explicitly reviewed publish scope."""
    if all_changes:
        _run_git(("add", "--all"), cwd=root)
        return
    for file_path in sorted(selected_files):
        _run_git(("add", "--", file_path.as_posix()), cwd=root)


def _ensure_staged_scope(status: GitStatus) -> None:
    """Ensure the final index is the complete publish scope."""
    if status.has_unstaged_scope:
        msg = "Refusing to publish because unstaged changes remain after staging."
        raise PublishError(msg)
    if not status.staged:
        msg = "No staged changes are available to commit."
        raise PublishError(msg)


def _git_status(root: Path) -> GitStatus:
    """Return staged, unstaged, and untracked paths from git."""
    staged = _git_paths(("diff", "--cached", "--name-only"), cwd=root)
    unstaged = _git_paths(("diff", "--name-only"), cwd=root)
    untracked = _git_paths(("ls-files", "--others", "--exclude-standard"), cwd=root)
    return GitStatus(staged=staged, unstaged=unstaged, untracked=untracked)


def _git_paths(command: tuple[str, ...], *, cwd: Path) -> frozenset[Path]:
    """Return newline-delimited git paths as relative Path objects."""
    output = _git_capture(command, cwd=cwd)
    return frozenset(Path(line) for line in output.splitlines() if line)


def _git_capture(command: tuple[str, ...], *, cwd: Path) -> str:
    """Run git and return stripped stdout."""
    result = _run_git(command, cwd=cwd, capture=True)
    return result.stdout.strip()


def _run_git(
    command: tuple[str, ...],
    *,
    cwd: Path,
    capture: bool = False,
) -> GitCommandResult:
    """Run one git command without shell execution."""
    executable = shutil.which("git")
    if executable is None:
        msg = "Executable not found: git"
        raise PublishError(msg)
    result = asyncio.run(
        _run_git_process(
            (executable, *command),
            cwd=cwd,
            capture=capture,
        )
    )
    if result.returncode == 0:
        return result
    details = (result.stderr or result.stdout).strip()
    msg = f"Git command failed: git {' '.join(command)}"
    if details:
        msg = f"{msg}\n{details}"
    raise PublishError(msg)


async def _run_git_process(
    command: tuple[str, ...],
    *,
    cwd: Path,
    capture: bool,
) -> GitCommandResult:
    """Run one git subprocess and capture output when requested."""
    stdout_target = asyncio.subprocess.PIPE if capture else None
    stderr_target = asyncio.subprocess.PIPE
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        stdout=stdout_target,
        stderr=stderr_target,
    )
    stdout_bytes, stderr_bytes = await process.communicate()
    return GitCommandResult(
        returncode=process.returncode or 0,
        stdout=_decode_process_output(stdout_bytes),
        stderr=_decode_process_output(stderr_bytes),
    )


def _decode_process_output(output: bytes | None) -> str:
    """Decode optional process output."""
    if output is None:
        return ""
    return output.decode(errors="replace")
