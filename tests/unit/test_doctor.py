"""Tests for generated project diagnostics."""

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from typer.testing import CliRunner

from scaffold_guard import doctor
from scaffold_guard.cli import app
from scaffold_guard.doctor import run_doctor
from scaffold_guard.manifest import MANIFEST_RELATIVE_PATH, load_manifest, write_manifest

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


def test_doctor_cli_reports_missing_path_without_traceback(tmp_path: Path) -> None:
    """Missing doctor paths produce clean diagnostics instead of a Rich traceback."""
    missing_path = tmp_path / "missing"

    result = CliRunner().invoke(app, ["doctor", "--path", str(missing_path)])

    assert result.exit_code == COMMAND_FAILED
    assert "scaffold-guard doctor: failed" in result.output
    assert "- project-root: error" in result.output
    assert f"Project root missing: {missing_path}" in result.output
    assert "- git-repository: warning" in result.output
    assert "Traceback" not in result.output


def test_doctor_cli_reports_file_path_without_traceback(tmp_path: Path) -> None:
    """File doctor paths produce clean diagnostics instead of a Rich traceback."""
    file_path = tmp_path / "not-a-directory"
    file_path.write_text("not a directory\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["doctor", "--path", str(file_path)])

    assert result.exit_code == COMMAND_FAILED
    assert "scaffold-guard doctor: failed" in result.output
    assert "- project-root: error" in result.output
    assert f"Project root is not a directory: {file_path}" in result.output
    assert "- git-repository: warning" in result.output
    assert "Traceback" not in result.output


def test_doctor_cli_json_reports_missing_path_without_traceback(tmp_path: Path) -> None:
    """Doctor JSON keeps structured invalid-path diagnostics without traceback output."""
    missing_path = tmp_path / "missing"

    result = CliRunner().invoke(app, ["doctor", "--path", str(missing_path), "--json"])

    payload = cast("dict[str, object]", json.loads(result.output))
    checks = cast("list[dict[str, object]]", payload["checks"])
    check_by_id = {str(check["id"]): check for check in checks}

    assert result.exit_code == COMMAND_FAILED
    assert payload["ok"] is False
    assert payload["path"] == str(missing_path)
    assert check_by_id["project-root"]["ok"] is False
    assert check_by_id["git-repository"]["severity"] == "warning"
    assert "Traceback" not in result.output


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


def test_doctor_reports_missing_codex_adapter_support_file(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Doctor treats missing Codex support scripts as adapter failures."""
    project_dir = generated_project(tmp_path, agent="codex")
    (project_dir / ".codex/hooks/workflow-evidence.sh").unlink()

    def fake_which(name: str) -> str:
        return f"/usr/bin/{name}"

    async def fake_run_git(git_path: str, root: Path) -> bool:
        assert git_path == "/usr/bin/git"
        assert root == project_dir
        return True

    monkeypatch.setattr("scaffold_guard.doctor.shutil.which", fake_which)
    monkeypatch.setattr(doctor, "_run_git", fake_run_git)

    report = run_doctor(project_dir)
    checks = {check.id: check for check in report.checks}

    assert not report.ok
    assert not checks["codex-adapter"].ok


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
    assert "gitlab-ci" not in check_ids


def test_doctor_warns_for_present_deselected_manifest_record(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    replace_text: Callable[[Path, str, str], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Doctor reports a present deselected managed file as a non-failing orphan."""
    project_dir = generated_project(tmp_path, agent="codex")
    replace_text(
        project_dir / "scaffold-guard.toml",
        "github_actions = true",
        "github_actions = false",
    )
    _stub_doctor_environment(monkeypatch, project_dir)

    report = run_doctor(project_dir)
    orphan_checks = [check for check in report.checks if check.id == "managed-file-orphan"]

    assert report.ok
    assert orphan_checks
    assert all(check.severity == "warning" for check in orphan_checks)
    assert any("remains in place" in check.message for check in orphan_checks)


def test_doctor_warns_for_missing_deselected_manifest_record(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    replace_text: Callable[[Path, str, str], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Doctor reports an absent deselected managed file as a non-failing orphan."""
    project_dir = generated_project(tmp_path, agent="codex")
    replace_text(
        project_dir / "scaffold-guard.toml",
        "github_actions = true",
        "github_actions = false",
    )
    for path in sorted((project_dir / ".github").rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    (project_dir / ".github").rmdir()
    _stub_doctor_environment(monkeypatch, project_dir)

    report = run_doctor(project_dir)
    orphan_checks = [check for check in report.checks if check.id == "managed-file-orphan"]

    assert report.ok
    assert orphan_checks
    assert all(check.severity == "warning" for check in orphan_checks)
    assert any("is already absent" in check.message for check in orphan_checks)


def test_doctor_errors_for_missing_v02_manifest(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Doctor fails a versioned project whose managed-file manifest is absent."""
    project_dir = generated_project(tmp_path)
    (project_dir / MANIFEST_RELATIVE_PATH).unlink()
    _stub_doctor_environment(monkeypatch, project_dir)

    report = run_doctor(project_dir)
    check = _managed_manifest_check(report)

    assert not report.ok
    assert not check.ok
    assert "requires a managed-file manifest" in check.message


def test_doctor_errors_for_malformed_manifest(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Doctor reports malformed manifest JSON without crashing."""
    project_dir = generated_project(tmp_path)
    (project_dir / MANIFEST_RELATIVE_PATH).write_text("{not-json", encoding="utf-8")
    _stub_doctor_environment(monkeypatch, project_dir)

    report = run_doctor(project_dir)
    check = _managed_manifest_check(report)

    assert not report.ok
    assert "manifest is invalid" in check.message.lower()


def test_doctor_errors_for_manifest_metadata_mismatch(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    replace_text: Callable[[Path, str, str], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Doctor retains strict manifest/config metadata agreement."""
    project_dir = generated_project(tmp_path)
    replace_text(project_dir / "scaffold-guard.toml", "claude = true", "claude = false")
    _stub_doctor_environment(monkeypatch, project_dir)

    report = run_doctor(project_dir)
    check = _managed_manifest_check(report)

    assert not report.ok
    assert "metadata does not match" in check.message


@pytest.mark.parametrize("mutation", ["missing", "drift"])
def test_doctor_errors_for_selected_managed_file_integrity(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    """Selected managed files remain error-level when missing or drifted."""
    project_dir = generated_project(tmp_path)
    target = project_dir / ".claude/rules/testing.md"
    if mutation == "missing":
        target.unlink()
    else:
        target.write_bytes(target.read_bytes() + b"# local edit\n")
    _stub_doctor_environment(monkeypatch, project_dir)

    report = run_doctor(project_dir)
    check = _managed_manifest_check(report)

    assert not report.ok
    assert "Manifest file" in check.message


def test_doctor_errors_for_symlinked_managed_parent(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Doctor rejects selected managed files beneath a symlinked parent directory."""
    project_dir = generated_project(tmp_path)
    codex_dir = project_dir / ".codex"
    internal_codex = project_dir / "local-codex"
    codex_dir.rename(internal_codex)
    codex_dir.symlink_to(internal_codex, target_is_directory=True)
    _stub_doctor_environment(monkeypatch, project_dir)

    report = run_doctor(project_dir)
    check = _managed_manifest_check(report)

    assert not report.ok
    assert not check.ok
    assert "symbolic-link component" in check.message


def test_doctor_errors_for_selected_manifest_record_omission(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Doctor errors when a selected managed path has no manifest record."""
    project_dir = generated_project(tmp_path)
    manifest_path = project_dir / MANIFEST_RELATIVE_PATH
    manifest = load_manifest(manifest_path)
    write_manifest(
        manifest_path,
        replace(
            manifest,
            files=tuple(file for file in manifest.files if file.path != ".claude/rules/testing.md"),
        ),
    )
    _stub_doctor_environment(monkeypatch, project_dir)

    report = run_doctor(project_dir)
    check = _managed_manifest_check(report)

    assert not report.ok
    assert "missing from manifest" in check.message


def test_doctor_warns_for_manifestless_legacy_project(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy projects receive upgrade guidance without an error-level manifest check."""
    project_dir = generated_project(tmp_path)
    config_path = project_dir / "scaffold-guard.toml"
    lines = config_path.read_text(encoding="utf-8").splitlines()
    start = lines.index("[scaffold_guard]")
    end = lines.index("[agents]")
    config_path.write_text("\n".join((*lines[:start], *lines[end:])) + "\n", encoding="utf-8")
    (project_dir / MANIFEST_RELATIVE_PATH).unlink()
    _stub_doctor_environment(monkeypatch, project_dir)

    report = run_doctor(project_dir)
    check = _managed_manifest_check(report)

    assert report.ok
    assert not check.ok
    assert check.severity == "warning"
    assert "run upgrade" in check.message


def test_doctor_allows_legacy_metadata_with_existing_manifest(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy metadata treats an already-present manifest as informational."""
    project_dir = generated_project(tmp_path)
    config_path = project_dir / "scaffold-guard.toml"
    lines = config_path.read_text(encoding="utf-8").splitlines()
    start = lines.index("[scaffold_guard]")
    end = lines.index("[agents]")
    config_path.write_text("\n".join((*lines[:start], *lines[end:])) + "\n", encoding="utf-8")
    _stub_doctor_environment(monkeypatch, project_dir)

    report = run_doctor(project_dir)
    check = _managed_manifest_check(report)

    assert report.ok
    assert check.ok
    assert check.severity == "info"


def test_doctor_minimal_profile_allows_missing_pyproject(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Minimal doctor diagnostics retain their optional-pyproject environment check."""
    project_dir = generated_project(tmp_path, profile="minimal")
    (project_dir / "pyproject.toml").unlink()
    _stub_doctor_environment(monkeypatch, project_dir)

    report = run_doctor(project_dir)
    checks = {check.id: check for check in report.checks}

    assert checks["pyproject"].ok
    assert "not required" in checks["pyproject"].message


def test_doctor_reports_gitlab_ci(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Doctor reports GitLab CI when selected."""
    project_dir = generated_project(tmp_path, ci="gitlab")

    def fake_which(name: str) -> str:
        return f"/usr/bin/{name}"

    async def fake_run_git(git_path: str, root: Path) -> bool:
        assert git_path == "/usr/bin/git"
        assert root == project_dir
        return True

    monkeypatch.setattr("scaffold_guard.doctor.shutil.which", fake_which)
    monkeypatch.setattr(doctor, "_run_git", fake_run_git)

    report = run_doctor(project_dir)
    checks = {check.id: check for check in report.checks}

    assert report.ok
    assert "github-actions" not in checks
    assert checks["gitlab-ci"].ok


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


def test_doctor_allows_typescript_profile_without_pyproject_or_uv(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TypeScript-only diagnostics require npm but do not require pyproject or uv."""
    project_dir = generated_project(tmp_path, profile="typescript")

    def fake_which(name: str) -> str:
        assert name != "uv"
        return f"/usr/bin/{name}"

    async def fake_run_git(git_path: str, root: Path) -> bool:
        assert git_path == "/usr/bin/git"
        assert root == project_dir
        return True

    monkeypatch.setattr("scaffold_guard.doctor.shutil.which", fake_which)
    monkeypatch.setattr(doctor, "_run_git", fake_run_git)

    report = run_doctor(project_dir)
    checks = {check.id: check for check in report.checks}

    assert report.ok
    assert checks["pyproject"].ok
    assert checks["npm-available"].ok
    assert "uv-available" not in checks
    assert checks["typescript-source-directory"].ok


def test_doctor_reports_monorepo_language_directories(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Monorepo diagnostics check both Python and TypeScript package directories."""
    project_dir = generated_project(tmp_path, profile="monorepo")

    def fake_which(name: str) -> str:
        return f"/usr/bin/{name}"

    async def fake_run_git(git_path: str, root: Path) -> bool:
        assert git_path == "/usr/bin/git"
        assert root == project_dir
        return True

    monkeypatch.setattr("scaffold_guard.doctor.shutil.which", fake_which)
    monkeypatch.setattr(doctor, "_run_git", fake_run_git)

    report = run_doctor(project_dir)
    checks = {check.id: check for check in report.checks}

    assert report.ok
    assert checks["uv-available"].ok
    assert checks["npm-available"].ok
    assert checks["python-package-directory"].ok
    assert checks["typescript-package-directory"].ok


def _stub_doctor_environment(monkeypatch: pytest.MonkeyPatch, project_dir: Path) -> None:
    """Make executable and git diagnostics deterministic for manifest tests."""

    def fake_which(name: str) -> str:
        return f"/usr/bin/{name}"

    async def fake_run_git(git_path: str, root: Path) -> bool:
        assert git_path == "/usr/bin/git"
        assert root == project_dir
        return True

    monkeypatch.setattr("scaffold_guard.doctor.shutil.which", fake_which)
    monkeypatch.setattr(doctor, "_run_git", fake_run_git)


def _managed_manifest_check(report: doctor.DoctorReport) -> doctor.DoctorCheck:
    """Return the primary managed-file manifest diagnostic."""
    return next(check for check in report.checks if check.id == "managed-file-manifest")
