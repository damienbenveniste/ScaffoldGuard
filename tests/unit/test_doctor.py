"""Tests for generated project diagnostics."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from typer.testing import CliRunner

from scaffold_guard import doctor
from scaffold_guard.cli import app
from scaffold_guard.doctor import run_doctor

SUCCESS = 0
COMMAND_FAILED = 1


def test_doctor_report_allows_git_repository_warning(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A generated project can pass doctor while warning about missing git state."""
    project_dir = generated_project(tmp_path)

    def fake_which(name: str) -> str:
        return f"/usr/bin/{name}"

    async def fake_run_git(git_path: str, root: Path) -> bool:
        assert git_path == "/usr/bin/git"
        assert root == project_dir
        return False

    monkeypatch.setattr("scaffold_guard.doctor.shutil.which", fake_which)
    monkeypatch.setattr(doctor, "_run_git", fake_run_git)

    report = run_doctor(project_dir)
    checks = {check.id: check for check in report.checks}
    payload = report.to_json()

    assert report.ok
    assert payload["ok"] is True
    assert checks["scaffold-guard-config"].ok
    assert checks["git-repository"].severity == "warning"
    assert not checks["git-repository"].ok


def test_doctor_cli_json_reports_missing_generated_config(tmp_path: Path) -> None:
    """Doctor JSON includes generated config errors and exits non-zero."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["doctor", "--path", str(tmp_path), "--json"])

    payload = cast("dict[str, object]", json.loads(result.output))
    checks = cast("list[dict[str, object]]", payload["checks"])

    assert result.exit_code == COMMAND_FAILED
    assert payload["ok"] is False
    assert any(check["id"] == "scaffold-guard-config" and not check["ok"] for check in checks)


def test_doctor_text_reports_successful_generated_project(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Doctor text mode lists successful generated-project diagnostics."""
    project_dir = generated_project(tmp_path, agent="codex")

    def fake_which(name: str) -> str:
        return f"/usr/bin/{name}"

    async def fake_run_git(git_path: str, root: Path) -> bool:
        assert git_path == "/usr/bin/git"
        assert root == project_dir
        return True

    monkeypatch.setattr("scaffold_guard.doctor.shutil.which", fake_which)
    monkeypatch.setattr(doctor, "_run_git", fake_run_git)

    result = CliRunner().invoke(app, ["doctor", "--path", str(project_dir)])

    assert result.exit_code == SUCCESS, result.output
    assert "scaffold-guard doctor: ok" in result.output
    assert "- scaffold-guard-config: ok" in result.output


def test_doctor_detects_invalid_pyproject(tmp_path: Path) -> None:
    """Doctor identifies parse errors before generated-project checks."""
    (tmp_path / "pyproject.toml").write_text("[project\n", encoding="utf-8")

    report = run_doctor(tmp_path)
    checks = {check.id: check for check in report.checks}

    assert not checks["pyproject"].ok


def test_doctor_reports_missing_pyproject(tmp_path: Path) -> None:
    """Doctor reports a missing pyproject without crashing on other checks."""
    report = run_doctor(tmp_path)
    checks = {check.id: check for check in report.checks}

    assert not report.ok
    assert not checks["pyproject"].ok


def test_doctor_omits_disabled_adapter_and_ci_checks(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    replace_text: Callable[[Path, str, str], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Doctor only checks generated adapters and CI selected by config."""
    project_dir = generated_project(tmp_path, agent="codex")
    replace_text(
        project_dir / "scaffold-guard.toml",
        "github_actions = true",
        "github_actions = false",
    )

    def fake_which(name: str) -> str:
        return f"/usr/bin/{name}"

    async def fake_run_git(git_path: str, root: Path) -> bool:
        assert git_path == "/usr/bin/git"
        assert root == project_dir
        return True

    monkeypatch.setattr("scaffold_guard.doctor.shutil.which", fake_which)
    monkeypatch.setattr(doctor, "_run_git", fake_run_git)

    report = run_doctor(project_dir)
    check_ids = {check.id for check in report.checks}

    assert report.ok
    assert "claude-adapter" not in check_ids
    assert "cursor-adapter" not in check_ids
    assert "github-actions" not in check_ids


def test_doctor_warns_when_git_is_unavailable(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Git repository diagnostics degrade to a warning when git is absent."""

    def fake_which(name: str) -> str | None:
        if name == "git":
            return None
        return f"/usr/bin/{name}"

    monkeypatch.setattr("scaffold_guard.doctor.shutil.which", fake_which)

    project_dir = generated_project(tmp_path)
    report = run_doctor(project_dir)
    checks = {check.id: check for check in report.checks}

    assert checks["git-repository"].severity == "warning"
    assert not checks["git-repository"].ok


def test_doctor_allows_minimal_profile_without_package_files(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Minimal profile diagnostics do not require pyproject or package source."""

    def fake_which(name: str) -> str:
        return f"/usr/bin/{name}"

    async def fake_run_git(git_path: str, root: Path) -> bool:
        assert git_path == "/usr/bin/git"
        assert root == project_dir
        return True

    project_dir = generated_project(tmp_path, profile="minimal")
    monkeypatch.setattr("scaffold_guard.doctor.shutil.which", fake_which)
    monkeypatch.setattr(doctor, "_run_git", fake_run_git)

    report = run_doctor(project_dir)
    check_ids = {check.id for check in report.checks}

    assert report.ok
    assert "package-import-directory" not in check_ids
    assert {check.id: check for check in report.checks}["pyproject"].ok
