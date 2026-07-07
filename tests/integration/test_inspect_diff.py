"""Integration tests for `scaffold-guard inspect-diff`."""

import asyncio
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
from typer.testing import CliRunner

from scaffold_guard.cli import app

SUCCESS = 0
CONFIG_ERROR = 2


@dataclass(frozen=True, slots=True)
class GitResult:
    """Small test result object for git commands."""

    returncode: int
    stdout: str
    stderr: str


def test_inspect_diff_source_change_requires_tests_and_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A source-only diff reports Python validation and test evidence."""
    monkeypatch.chdir(tmp_path)
    project_dir = _init_git_project(tmp_path)
    core_path = project_dir / "src/demo/core.py"
    core_path.write_text(
        core_path.read_text(encoding="utf-8") + '\n\ndef new_api() -> str:\n    return "ok"\n',
        encoding="utf-8",
    )
    _git(project_dir, "add", "src/demo/core.py")

    result = CliRunner().invoke(
        app,
        ["inspect-diff", "--path", str(project_dir), "--base", "HEAD"],
    )

    assert result.exit_code == SUCCESS, result.output
    assert "Diff impact summary" in result.output
    assert "package source: src/demo/core.py" in result.output
    assert "uv run mypy src tests" in result.output
    assert "tests changed or added for behavior change" in result.output


def test_inspect_diff_docs_only_json_is_deterministic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Docs-only JSON output contains only docs validation requirements."""
    monkeypatch.chdir(tmp_path)
    project_dir = _init_git_project(tmp_path)
    readme_path = project_dir / "README.md"
    readme_path.write_text(readme_path.read_text(encoding="utf-8") + "\nDocs update.\n")

    result = CliRunner().invoke(
        app,
        ["inspect-diff", "--path", str(project_dir), "--base", "HEAD", "--json"],
    )

    assert result.exit_code == SUCCESS, result.output
    payload = cast("dict[str, object]", json.loads(result.output))
    assert payload["changed_files"] == ["README.md"]
    assert payload["required_validation"] == ["uv run mkdocs build --strict", "git diff --check"]
    assert payload["required_evidence"] == ["final response lists validation commands run"]


def test_inspect_diff_pyproject_warns_about_lockfile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pyproject changes warn when uv.lock exists and is not changed."""
    monkeypatch.chdir(tmp_path)
    project_dir = _init_git_project(tmp_path)
    (project_dir / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    _git(project_dir, "add", "uv.lock")
    _git(project_dir, "commit", "-m", "add lockfile")
    pyproject_path = project_dir / "pyproject.toml"
    pyproject_path.write_text(pyproject_path.read_text(encoding="utf-8") + "\n# local change\n")

    result = CliRunner().invoke(
        app,
        ["inspect-diff", "--path", str(project_dir), "--base", "HEAD"],
    )

    assert result.exit_code == SUCCESS, result.output
    assert "uv lock or uv sync" in result.output
    assert "uv.lock exists but is not in the diff" in result.output


def test_inspect_diff_agent_rule_requires_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Agent rule diffs require `scaffold-guard check`."""
    monkeypatch.chdir(tmp_path)
    project_dir = _init_git_project(tmp_path)
    agents_path = project_dir / "AGENTS.md"
    agents_path.write_text(agents_path.read_text(encoding="utf-8") + "\n- Extra rule.\n")

    result = CliRunner().invoke(
        app,
        ["inspect-diff", "--path", str(project_dir), "--base", "HEAD"],
    )

    assert result.exit_code == SUCCESS, result.output
    assert "agent instructions: AGENTS.md" in result.output
    assert "scaffold-guard check" in result.output


def test_inspect_diff_non_git_path_exits_with_configuration_error(tmp_path: Path) -> None:
    """Non-git paths produce a clear configuration error."""
    result = CliRunner().invoke(app, ["inspect-diff", "--path", str(tmp_path)])

    assert result.exit_code == CONFIG_ERROR
    assert "not a git repository" in result.output


def _init_git_project(tmp_path: Path) -> Path:
    """Generate a project and commit its initial state."""
    result = CliRunner().invoke(
        app,
        ["init", "demo", "--profile", "package"],
        catch_exceptions=False,
    )
    assert result.exit_code == SUCCESS, result.output
    project_dir = tmp_path / "demo"
    _git(project_dir, "init")
    _git(project_dir, "config", "user.email", "agent@example.com")
    _git(project_dir, "config", "user.name", "ScaffoldGuard")
    _git(project_dir, "add", ".")
    _git(project_dir, "commit", "-m", "initial")
    return project_dir


def _git(cwd: Path, *args: str) -> None:
    """Run a git command in a test repository."""
    git_path = shutil.which("git")
    assert git_path is not None
    result = asyncio.run(_run_git(git_path, cwd, args))
    assert result.returncode == SUCCESS, result.stderr


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
