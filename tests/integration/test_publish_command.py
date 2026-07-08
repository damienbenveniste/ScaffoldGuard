"""Integration tests for `scaffold-guard publish`."""

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest
from typer.testing import CliRunner

from scaffold_guard.cli import app

SUCCESS = 0


@dataclass(frozen=True, slots=True)
class GitResult:
    """Small test result object for git commands."""

    returncode: int
    stdout: str
    stderr: str


def test_publish_cli_commits_and_pushes_to_local_remote(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public publish command works against a local git remote."""
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        app,
        ["init", "demo", "--profile", "minimal", "--agent", "codex"],
        catch_exceptions=False,
    )
    assert result.exit_code == SUCCESS, result.output
    project_dir = tmp_path / "demo"
    remote_dir = tmp_path / "remote.git"

    _git(project_dir, "init")
    _git(project_dir, "checkout", "-b", "feature")
    _git(project_dir, "config", "user.email", "agent@example.com")
    _git(project_dir, "config", "user.name", "ScaffoldGuard")
    _git(project_dir, "add", ".")
    _git(project_dir, "commit", "-m", "initial")
    _git(tmp_path, "init", "--bare", "remote.git")
    _git(project_dir, "remote", "add", "origin", str(remote_dir))
    readme_path = project_dir / "README.md"
    readme_path.write_text(
        f"{readme_path.read_text(encoding='utf-8')}\nPublished update.\n",
        encoding="utf-8",
    )

    publish_result = CliRunner().invoke(
        app,
        [
            "publish",
            "--path",
            str(project_dir),
            "--message",
            "Update README",
            "--all",
            "--quick",
            "--remote",
            "origin",
            "--branch",
            "feature",
        ],
        catch_exceptions=False,
    )

    assert publish_result.exit_code == SUCCESS, publish_result.output
    assert "scaffold-guard publish: committed and pushed" in publish_result.output
    assert "target: origin/feature" in publish_result.output
    assert _git_stdout(project_dir, "status", "--short") == ""
    assert "Update README" in _git_stdout(remote_dir, "log", "--oneline", "feature", "-1")


def _git(cwd: Path, *args: str) -> None:
    """Run a git command in a test repository."""
    result = _git_result(cwd, *args)
    assert result.returncode == SUCCESS, result.stderr


def _git_stdout(cwd: Path, *args: str) -> str:
    """Run a git command and return stripped stdout."""
    result = _git_result(cwd, *args)
    assert result.returncode == SUCCESS, result.stderr
    return result.stdout.strip()


def _git_result(cwd: Path, *args: str) -> GitResult:
    """Run git asynchronously in tests."""
    git_path = shutil.which("git")
    assert git_path is not None
    return asyncio.run(_run_git(git_path, cwd, args))


async def _run_git(executable: str, cwd: Path, args: tuple[str, ...]) -> GitResult:
    """Run git asynchronously in tests."""
    process = await asyncio.create_subprocess_exec(
        executable,
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return GitResult(
        returncode=process.returncode or 0,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
    )
