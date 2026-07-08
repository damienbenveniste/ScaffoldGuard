"""Tests for audited generated-project publishing."""

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from typer.testing import CliRunner

import scaffold_guard.cli as cli_module
import scaffold_guard.publish as publish_module
from scaffold_guard.cli import app
from scaffold_guard.publish import (
    GitCommandResult,
    GitStatus,
    PublishError,
    PublishSummary,
    publish_changes,
)
from scaffold_guard.validation import CommandStatus, ValidationReport

SUCCESS = 0
CONFIG_ERROR = 2


def test_publish_all_validates_stages_commits_and_pushes(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The audited publish path validates before staging and pushing."""
    project_dir = generated_project(tmp_path, profile="minimal")
    validation_calls: list[tuple[Path, bool, bool]] = []
    git_calls: list[tuple[str, ...]] = []
    statuses = iter(
        (
            GitStatus(
                staged=frozenset(),
                unstaged=frozenset({Path("README.md")}),
                untracked=frozenset({Path("notes.md")}),
            ),
            GitStatus(
                staged=frozenset({Path("README.md"), Path("notes.md")}),
                unstaged=frozenset(),
                untracked=frozenset(),
            ),
        )
    )

    def fake_run_validation(path: Path, *, quick: bool, capture: bool) -> ValidationReport:
        validation_calls.append((path, quick, capture))
        return ValidationReport(
            path=project_dir,
            quick=quick,
            commands=(CommandStatus(command=("scaffold-guard", "check"), exit_code=SUCCESS),),
        )

    def fake_git_capture(command: tuple[str, ...], *, cwd: Path) -> str:
        assert cwd == project_dir
        if command == ("rev-parse", "--show-toplevel"):
            return str(project_dir)
        raise AssertionError(f"unexpected git capture: {command}")

    def fake_git_status(root: Path) -> GitStatus:
        assert root == project_dir
        return next(statuses)

    def fake_run_git(
        command: tuple[str, ...],
        *,
        cwd: Path,
        capture: bool = False,
    ) -> GitCommandResult:
        assert cwd == project_dir
        assert not capture
        git_calls.append(command)
        return GitCommandResult(returncode=SUCCESS)

    monkeypatch.setattr(publish_module, "run_validation", fake_run_validation)
    monkeypatch.setattr(publish_module, "_git_capture", fake_git_capture)
    monkeypatch.setattr(publish_module, "_git_status", fake_git_status)
    monkeypatch.setattr(publish_module, "_run_git", fake_run_git)

    summary = publish_changes(
        project_dir,
        message="Ship reviewed update",
        all_changes=True,
        files=(),
        remote="origin",
        branch="feature",
        quick=False,
        push_only=False,
    )

    assert summary.commit_created
    assert summary.remote == "origin"
    assert summary.branch == "feature"
    assert validation_calls == [(project_dir, False, False)]
    assert git_calls == [
        ("add", "--all"),
        ("commit", "-m", "Ship reviewed update"),
        ("push", "origin", "HEAD:feature"),
    ]


def test_publish_refuses_mixed_staged_and_unstaged_scope(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Publishing stops when staged and unstaged work are mixed."""
    project_dir = generated_project(tmp_path, profile="minimal")
    git_calls: list[tuple[str, ...]] = []

    _patch_successful_publish_environment(
        monkeypatch,
        project_dir,
        status=GitStatus(
            staged=frozenset({Path("README.md")}),
            unstaged=frozenset({Path("AGENTS.md")}),
            untracked=frozenset(),
        ),
        git_calls=git_calls,
    )

    with pytest.raises(PublishError, match="mixed staged and unstaged"):
        publish_changes(
            project_dir,
            message="Update docs",
            all_changes=True,
            files=(),
            remote="origin",
            branch="feature",
            quick=True,
            push_only=False,
        )

    assert git_calls == []


def test_publish_file_selection_refuses_unselected_dirty_files(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A file-scoped publish must cover the full dirty scope."""
    project_dir = generated_project(tmp_path, profile="minimal")
    _patch_successful_publish_environment(
        monkeypatch,
        project_dir,
        status=GitStatus(
            staged=frozenset(),
            unstaged=frozenset({Path("README.md")}),
            untracked=frozenset({Path("notes.md")}),
        ),
        git_calls=[],
    )

    with pytest.raises(PublishError, match="outside --file selection"):
        publish_changes(
            project_dir,
            message="Update docs",
            all_changes=False,
            files=(Path("README.md"),),
            remote="origin",
            branch="feature",
            quick=True,
            push_only=False,
        )


def test_publish_push_only_requires_clean_working_tree(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Push-only publishing refuses local uncommitted changes."""
    project_dir = generated_project(tmp_path, profile="minimal")
    _patch_successful_publish_environment(
        monkeypatch,
        project_dir,
        status=GitStatus(
            staged=frozenset(),
            unstaged=frozenset({Path("README.md")}),
            untracked=frozenset(),
        ),
        git_calls=[],
    )

    with pytest.raises(PublishError, match="--push-only with uncommitted changes"):
        publish_changes(
            project_dir,
            message=None,
            all_changes=False,
            files=(),
            remote="origin",
            branch="feature",
            quick=True,
            push_only=True,
        )


def test_publish_push_only_clean_tree_pushes_without_commit(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Push-only publishing validates and pushes when the tree is clean."""
    project_dir = generated_project(tmp_path, profile="minimal")
    git_calls: list[tuple[str, ...]] = []
    _patch_successful_publish_environment(
        monkeypatch,
        project_dir,
        status=GitStatus(staged=frozenset(), unstaged=frozenset(), untracked=frozenset()),
        git_calls=git_calls,
    )

    summary = publish_changes(
        project_dir,
        message=None,
        all_changes=False,
        files=(),
        remote="origin",
        branch="feature",
        quick=True,
        push_only=True,
    )

    assert not summary.commit_created
    assert git_calls == [("push", "origin", "HEAD:feature")]


def test_publish_uses_configured_upstream_when_target_is_not_explicit(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Publishing defaults to the configured upstream remote and branch."""
    project_dir = generated_project(tmp_path, profile="minimal")
    git_calls: list[tuple[str, ...]] = []
    statuses = iter(
        (
            GitStatus(
                staged=frozenset({Path("README.md")}),
                unstaged=frozenset(),
                untracked=frozenset(),
            ),
            GitStatus(
                staged=frozenset({Path("README.md")}),
                unstaged=frozenset(),
                untracked=frozenset(),
            ),
        )
    )

    _patch_validation(monkeypatch, project_dir)

    def fake_git_capture(command: tuple[str, ...], *, cwd: Path) -> str:
        assert cwd == project_dir
        if command == ("rev-parse", "--show-toplevel"):
            return str(project_dir)
        if command == ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"):
            return "origin/main"
        raise AssertionError(f"unexpected git capture: {command}")

    def fake_git_status(root: Path) -> GitStatus:
        assert root == project_dir
        return next(statuses)

    def fake_run_git(
        command: tuple[str, ...],
        *,
        cwd: Path,
        capture: bool = False,
    ) -> GitCommandResult:
        assert cwd == project_dir
        assert not capture
        git_calls.append(command)
        return GitCommandResult(returncode=SUCCESS)

    monkeypatch.setattr(publish_module, "_git_capture", fake_git_capture)
    monkeypatch.setattr(publish_module, "_git_status", fake_git_status)
    monkeypatch.setattr(publish_module, "_run_git", fake_run_git)

    summary = publish_changes(
        project_dir,
        message="Update README",
        all_changes=False,
        files=(),
        remote=None,
        branch=None,
        quick=True,
        push_only=False,
    )

    assert summary.remote == "origin"
    assert summary.branch == "main"
    assert git_calls == [
        ("commit", "-m", "Update README"),
        ("push", "origin", "HEAD:main"),
    ]


def test_publish_defaults_to_current_branch_when_upstream_is_missing(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Publishing falls back to origin and the current branch without upstream."""
    project_dir = generated_project(tmp_path, profile="minimal")
    git_calls: list[tuple[str, ...]] = []
    _patch_validation(monkeypatch, project_dir)

    def fake_git_capture(command: tuple[str, ...], *, cwd: Path) -> str:
        assert cwd == project_dir
        if command == ("rev-parse", "--show-toplevel"):
            return str(project_dir)
        if command == ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"):
            raise PublishError("no upstream")
        if command == ("branch", "--show-current"):
            return "feature"
        raise AssertionError(f"unexpected git capture: {command}")

    monkeypatch.setattr(publish_module, "_git_capture", fake_git_capture)

    def fake_clean_git_status(root: Path) -> GitStatus:
        assert root == project_dir
        return GitStatus(staged=frozenset(), unstaged=frozenset(), untracked=frozenset())

    monkeypatch.setattr(publish_module, "_git_status", fake_clean_git_status)

    def fake_run_git(
        command: tuple[str, ...],
        *,
        cwd: Path,
        capture: bool = False,
    ) -> GitCommandResult:
        assert cwd == project_dir
        assert not capture
        git_calls.append(command)
        return GitCommandResult(returncode=SUCCESS)

    monkeypatch.setattr(publish_module, "_run_git", fake_run_git)

    summary = publish_changes(
        project_dir,
        message=None,
        all_changes=False,
        files=(),
        remote=None,
        branch=None,
        quick=True,
        push_only=True,
    )

    assert summary.remote == "origin"
    assert summary.branch == "feature"
    assert git_calls == [("push", "origin", "HEAD:feature")]


def test_publish_refuses_nested_generated_project(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Publishing refuses when scaffold-guard.toml is below the git root."""
    project_dir = generated_project(tmp_path, profile="minimal")

    def fake_git_capture(command: tuple[str, ...], *, cwd: Path) -> str:
        assert cwd == project_dir
        assert command == ("rev-parse", "--show-toplevel")
        return str(tmp_path)

    monkeypatch.setattr(publish_module, "_git_capture", fake_git_capture)

    with pytest.raises(PublishError, match="nested generated project"):
        publish_changes(
            project_dir,
            message="Update",
            all_changes=True,
            files=(),
            remote="origin",
            branch="feature",
            quick=True,
            push_only=False,
        )


def test_publish_refuses_validation_failure(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Publishing stops before git mutation when validation fails."""
    project_dir = generated_project(tmp_path, profile="minimal")

    def fake_run_validation(path: Path, *, quick: bool, capture: bool) -> ValidationReport:
        assert path == project_dir
        assert quick
        assert not capture
        return ValidationReport(
            path=project_dir,
            quick=quick,
            commands=(CommandStatus(command=("scaffold-guard", "check"), exit_code=CONFIG_ERROR),),
        )

    monkeypatch.setattr(publish_module, "run_validation", fake_run_validation)

    def fake_git_capture(command: tuple[str, ...], *, cwd: Path) -> str:
        assert command == ("rev-parse", "--show-toplevel")
        assert cwd == project_dir
        return str(project_dir)

    monkeypatch.setattr(publish_module, "_git_capture", fake_git_capture)

    with pytest.raises(PublishError, match="Validation failed before publish"):
        publish_changes(
            project_dir,
            message="Update",
            all_changes=True,
            files=(),
            remote="origin",
            branch="feature",
            quick=True,
            push_only=False,
        )


@pytest.mark.parametrize("message", [None, "", "   "])
def test_publish_requires_commit_message_unless_push_only(message: str | None) -> None:
    """Commit publishing requires an explicit non-empty message."""
    normalize_commit_message = cast(
        "Callable[..., str]",
        _private_callable("_normalize_commit_message"),
    )
    with pytest.raises(PublishError, match="message"):
        normalize_commit_message(message, push_only=False)


@pytest.mark.parametrize(
    "file_path",
    [Path.cwd() / "file.txt", Path(), Path("../file.txt")],
)
def test_publish_rejects_unsafe_file_selection(file_path: Path) -> None:
    """File-scoped publishing accepts only relative project paths."""
    normalize_selected_files = cast(
        "Callable[..., frozenset[Path]]",
        _private_callable("_normalize_selected_files"),
    )
    with pytest.raises(PublishError, match=r"file path|file paths"):
        normalize_selected_files((file_path,))


def test_publish_scope_validation_rejects_ambiguous_dirty_states() -> None:
    """Publish scope validation catches non-explicit or inconsistent scopes."""
    clean = GitStatus(staged=frozenset(), unstaged=frozenset(), untracked=frozenset())
    unstaged = GitStatus(
        staged=frozenset(),
        unstaged=frozenset({Path("README.md")}),
        untracked=frozenset(),
    )
    ensure_publishable_status = cast(
        "Callable[..., None]",
        _private_callable("_ensure_publishable_status"),
    )

    with pytest.raises(PublishError, match="No changes"):
        ensure_publishable_status(
            clean,
            all_changes=False,
            selected_files=frozenset(),
        )
    with pytest.raises(PublishError, match="either --all or --file"):
        ensure_publishable_status(
            unstaged,
            all_changes=True,
            selected_files=frozenset({Path("README.md")}),
        )
    with pytest.raises(PublishError, match="explicit --all or --file"):
        ensure_publishable_status(
            unstaged,
            all_changes=False,
            selected_files=frozenset(),
        )
    with pytest.raises(PublishError, match="not dirty"):
        ensure_publishable_status(
            unstaged,
            all_changes=False,
            selected_files=frozenset({Path("README.md"), Path("missing.md")}),
        )


def test_publish_staging_checks_refuse_incomplete_index() -> None:
    """Final staged scope checks reject leftover or empty index states."""
    ensure_staged_scope = cast(
        "Callable[..., None]",
        _private_callable("_ensure_staged_scope"),
    )
    with pytest.raises(PublishError, match="unstaged changes remain"):
        ensure_staged_scope(
            GitStatus(
                staged=frozenset({Path("README.md")}),
                unstaged=frozenset({Path("AGENTS.md")}),
                untracked=frozenset(),
            )
        )
    with pytest.raises(PublishError, match="No staged changes"):
        ensure_staged_scope(
            GitStatus(staged=frozenset(), unstaged=frozenset(), untracked=frozenset())
        )


def test_publish_git_helpers_report_missing_executable_and_command_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Git helper errors are converted to publish errors."""

    def fake_which_missing(name: str) -> str | None:
        assert name == "git"
        return None

    monkeypatch.setattr(shutil, "which", fake_which_missing)
    run_git = cast("Callable[..., GitCommandResult]", _private_callable("_run_git"))
    with pytest.raises(PublishError, match="Executable not found"):
        run_git(("status",), cwd=tmp_path)

    async def fake_run_git_process(
        command: tuple[str, ...],
        *,
        cwd: Path,
        capture: bool,
    ) -> GitCommandResult:
        assert command == ("/usr/bin/git", "status")
        assert cwd == tmp_path
        assert not capture
        return GitCommandResult(returncode=CONFIG_ERROR, stderr="fatal")

    def fake_which(name: str) -> str | None:
        assert name == "git"
        return "/usr/bin/git"

    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr(publish_module, "_run_git_process", fake_run_git_process)
    with pytest.raises(PublishError, match="fatal"):
        run_git(("status",), cwd=tmp_path)


def test_publish_cli_reports_audited_publish_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public CLI exposes the audited publish path."""

    def fake_publish_changes(
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
        assert path == tmp_path
        assert message == "Update docs"
        assert all_changes
        assert files == ()
        assert remote is None
        assert branch is None
        assert not quick
        assert not push_only
        return PublishSummary(
            root=tmp_path,
            remote="origin",
            branch="feature",
            commit_created=True,
            validation=ValidationReport(path=tmp_path, quick=False, commands=()),
        )

    monkeypatch.setattr(cli_module, "publish_changes", fake_publish_changes)

    result = CliRunner().invoke(
        app,
        ["publish", "--path", str(tmp_path), "--message", "Update docs", "--all"],
    )

    assert result.exit_code == SUCCESS, result.output
    assert "scaffold-guard publish: committed and pushed" in result.output
    assert "target: origin/feature" in result.output


def test_publish_cli_reports_publish_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Publish errors use the generated-project configuration exit code."""

    def fake_publish_changes(
        _path: Path,
        *,
        message: str | None,
        all_changes: bool,
        files: tuple[Path, ...],
        remote: str | None,
        branch: str | None,
        quick: bool,
        push_only: bool,
    ) -> PublishSummary:
        _ = (message, all_changes, files, remote, branch, quick, push_only)
        raise PublishError("publish blocked")

    monkeypatch.setattr(cli_module, "publish_changes", fake_publish_changes)

    result = CliRunner().invoke(app, ["publish", "--path", str(tmp_path), "--push-only"])

    assert result.exit_code == CONFIG_ERROR
    assert "Error: publish blocked" in result.output


def _patch_successful_publish_environment(
    monkeypatch: pytest.MonkeyPatch,
    project_dir: Path,
    *,
    status: GitStatus,
    git_calls: list[tuple[str, ...]],
) -> None:
    """Patch validation and git helpers for a publish error-path test."""

    def fake_run_validation(path: Path, *, quick: bool, capture: bool) -> ValidationReport:
        assert path == project_dir
        assert capture is False
        return ValidationReport(
            path=project_dir,
            quick=quick,
            commands=(CommandStatus(command=("scaffold-guard", "check"), exit_code=SUCCESS),),
        )

    def fake_git_capture(command: tuple[str, ...], *, cwd: Path) -> str:
        assert cwd == project_dir
        if command == ("rev-parse", "--show-toplevel"):
            return str(project_dir)
        raise AssertionError(f"unexpected git capture: {command}")

    def fake_git_status(root: Path) -> GitStatus:
        assert root == project_dir
        return status

    def fake_run_git(
        command: tuple[str, ...],
        *,
        cwd: Path,
        capture: bool = False,
    ) -> GitCommandResult:
        assert cwd == project_dir
        assert not capture
        git_calls.append(command)
        return GitCommandResult(returncode=SUCCESS)

    monkeypatch.setattr(publish_module, "run_validation", fake_run_validation)
    monkeypatch.setattr(publish_module, "_git_capture", fake_git_capture)
    monkeypatch.setattr(publish_module, "_git_status", fake_git_status)
    monkeypatch.setattr(publish_module, "_run_git", fake_run_git)


def _patch_validation(
    monkeypatch: pytest.MonkeyPatch,
    project_dir: Path,
) -> None:
    """Patch validation to succeed for publish target-selection tests."""

    def fake_run_validation(path: Path, *, quick: bool, capture: bool) -> ValidationReport:
        assert path == project_dir
        assert capture is False
        return ValidationReport(
            path=project_dir,
            quick=quick,
            commands=(CommandStatus(command=("scaffold-guard", "check"), exit_code=SUCCESS),),
        )

    monkeypatch.setattr(publish_module, "run_validation", fake_run_validation)


def _private_callable(name: str) -> Callable[..., object]:
    """Return a private publish helper for focused branch coverage."""
    return cast("Callable[..., object]", getattr(publish_module, name))
