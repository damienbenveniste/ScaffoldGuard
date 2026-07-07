"""Tests for Milestone 6 command implementations."""

import json
import sys
from pathlib import Path
from typing import NoReturn, cast

import pytest
from typer.testing import CliRunner

import scaffold_guard.compile_rules as compile_rules_module
from scaffold_guard import doctor, validation
from scaffold_guard.checks.base import CheckConfigurationError
from scaffold_guard.cli import app
from scaffold_guard.compile_rules import (
    GENERATED_MARKER,
    compile_rules,
    selected_agent_files,
)
from scaffold_guard.doctor import run_doctor
from scaffold_guard.models import AgentChoice, InitOptions, ProfileChoice
from scaffold_guard.project_config import (
    GeneratedProjectConfig,
    ProjectConfigError,
    load_generated_project_config,
)
from scaffold_guard.scaffold import RenderedFile, build_init_options, scaffold_package_project
from scaffold_guard.validation import CommandStatus, validation_commands

SUCCESS = 0
COMMAND_FAILED = 1
CONFIG_ERROR = 2
EXECUTABLE_NOT_FOUND = 127


@pytest.mark.parametrize(
    ("agent", "expected_choice", "expected_flags"),
    [
        ("codex", "codex", {"codex": True, "claude": False, "cursor": False}),
        ("claude", "claude", {"codex": False, "claude": True, "cursor": False}),
        ("cursor", "cursor", {"codex": False, "claude": False, "cursor": True}),
        ("all", "all", {"codex": True, "claude": True, "cursor": True}),
    ],
)
def test_generated_project_config_round_trips_agent_selection(
    tmp_path: Path,
    agent: AgentChoice,
    expected_choice: AgentChoice,
    expected_flags: dict[str, bool],
) -> None:
    """Generated config exposes the fields needed by V1 commands."""
    project_dir = _generated_project(tmp_path, agent=agent)

    config = load_generated_project_config(project_dir)
    options = config.to_init_options(dry_run=True, force=False)
    payload = config.to_json()

    assert config.agent_choice == expected_choice
    assert options.agent == expected_choice
    assert options.target_dir == project_dir
    assert options.package_name == "demo"
    assert payload["name"] == "demo"
    assert payload["agents"] == expected_flags


def test_generated_project_config_rejects_missing_required_fields(tmp_path: Path) -> None:
    """Generated-project-only commands require a complete scaffold-guard.toml."""
    project_dir = _generated_project(tmp_path)
    (project_dir / "scaffold-guard.toml").write_text(
        "[project]\nname = 'demo'\n",
        encoding="utf-8",
    )

    with pytest.raises(ProjectConfigError, match="Missing required string config value"):
        load_generated_project_config(project_dir)


def test_generated_project_config_loads_minimal_profile(tmp_path: Path) -> None:
    """Generated config supports the guardrails-only minimal profile."""
    project_dir = _generated_project(tmp_path, profile="minimal")

    config = load_generated_project_config(project_dir)
    options = config.to_init_options(dry_run=True, force=False)

    assert config.profile == "minimal"
    assert options.profile == "minimal"
    assert not (project_dir / "pyproject.toml").exists()
    assert not (project_dir / "src").exists()


def test_generated_project_config_rejects_bad_profile_and_missing_coverage(
    tmp_path: Path,
) -> None:
    """Generated config validation reports unsupported profiles and missing integers."""
    project_dir = _generated_project(tmp_path)
    config_path = project_dir / "scaffold-guard.toml"
    original = config_path.read_text(encoding="utf-8")

    _replace_text(config_path, 'profile = "package"', 'profile = "application"')
    with pytest.raises(ProjectConfigError, match="Unsupported generated project profile"):
        load_generated_project_config(project_dir)

    config_path.write_text(
        original.replace("coverage_fail_under = 95\n", ""),
        encoding="utf-8",
    )
    with pytest.raises(ProjectConfigError, match="Missing required integer config value"):
        load_generated_project_config(project_dir)


def test_compile_rules_is_idempotent_and_reports_selected_files(tmp_path: Path) -> None:
    """Rule compilation can safely refresh generated agent instruction files."""
    project_dir = _generated_project(tmp_path)
    agents_path = project_dir / "AGENTS.md"
    initial_content = agents_path.read_text(encoding="utf-8")

    summary = compile_rules(project_dir, agent="all", dry_run=False, force=False)
    second_summary = compile_rules(project_dir, agent="all", dry_run=False, force=False)
    payload = summary.to_json()
    files = cast("list[str]", payload["files"])
    selected_files = selected_agent_files(load_generated_project_config(project_dir))

    assert not summary.dry_run
    assert Path("AGENTS.md") in summary.files
    assert Path("AGENTS.md") in second_summary.files
    assert "AGENTS.md" in files
    assert Path(".cursor/rules/python.mdc") in selected_files
    assert agents_path.read_text(encoding="utf-8") == initial_content
    assert agents_path.read_text(encoding="utf-8").count(GENERATED_MARKER) == 1


def test_compile_rules_refuses_manual_files_without_force(tmp_path: Path) -> None:
    """Manual instruction files are protected unless the user opts into overwrite."""
    project_dir = _generated_project(tmp_path)
    agents_path = project_dir / "AGENTS.md"
    agents_path.write_text("# Manual Rules\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="without --force"):
        compile_rules(project_dir, agent="codex", dry_run=False, force=False)

    summary = compile_rules(project_dir, agent="codex", dry_run=False, force=True)

    assert summary.files == (Path("AGENTS.md"),)
    assert GENERATED_MARKER in agents_path.read_text(encoding="utf-8")


def test_compile_rules_can_plan_missing_selected_adapter_files(tmp_path: Path) -> None:
    """Rule compilation can add selected adapter files that are not present yet."""
    project_dir = _generated_project(tmp_path, agent="codex")

    summary = compile_rules(project_dir, agent="claude", dry_run=True, force=False)

    assert Path("CLAUDE.md") in summary.files
    assert not (project_dir / "CLAUDE.md").exists()


def test_compile_rules_marks_unmarked_rendered_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rule compilation adds generated markers to unmarked rendered outputs."""
    project_dir = _generated_project(tmp_path)

    def fake_render_package_files(options: InitOptions) -> tuple[RenderedFile, ...]:
        assert options.agent == "all"
        return (
            RenderedFile(path=Path("CLAUDE.md"), content="@AGENTS.md\n"),
            RenderedFile(
                path=Path(".cursor/rules/python.mdc"),
                content='---\ndescription: Python\nglobs: "src/**/*.py"\n---\n# Python\n',
            ),
        )

    monkeypatch.setattr(compile_rules_module, "render_package_files", fake_render_package_files)

    summary = compile_rules(project_dir, agent="all", dry_run=False, force=True)
    claude_content = (project_dir / "CLAUDE.md").read_text(encoding="utf-8")
    cursor_content = (project_dir / ".cursor/rules/python.mdc").read_text(encoding="utf-8")

    assert summary.files == (Path("CLAUDE.md"), Path(".cursor/rules/python.mdc"))
    assert claude_content.startswith(f"{GENERATED_MARKER}\n\n@AGENTS.md")
    assert f"---\n{GENERATED_MARKER}\n\n# Python" in cursor_content


def test_compile_rules_cli_dry_run_leaves_files_unchanged(tmp_path: Path) -> None:
    """The public compile-rules dry-run path reports planned writes only."""
    project_dir = _generated_project(tmp_path)
    agents_path = project_dir / "AGENTS.md"
    agents_path.write_text("# Manual Rules\n", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "compile-rules",
            "--path",
            str(project_dir),
            "--agent",
            "codex",
            "--dry-run",
            "--force",
        ],
    )

    assert result.exit_code == SUCCESS, result.output
    assert "Planned agent instruction files" in result.output
    assert agents_path.read_text(encoding="utf-8") == "# Manual Rules\n"


def test_compile_rules_cli_reports_configuration_errors(tmp_path: Path) -> None:
    """The public compile-rules command reports missing generated config distinctly."""
    result = CliRunner().invoke(app, ["compile-rules", "--path", str(tmp_path)])

    assert result.exit_code == CONFIG_ERROR
    assert "Generated project config is missing" in result.output


def test_validation_commands_are_fixed_for_quick_and_full_profiles(tmp_path: Path) -> None:
    """Validation command planning uses project package and coverage settings."""
    project_dir = _generated_project(tmp_path)
    config = load_generated_project_config(project_dir)

    quick = validation_commands(config, quick=True)
    full = validation_commands(config, quick=False)

    assert quick == (
        ("uv", "run", "ruff", "format", "--check", "."),
        ("uv", "run", "ruff", "check", "."),
        ("uv", "run", "pytest", "tests/unit"),
        ("scaffold-guard", "check"),
    )
    assert ("uv", "run", "mypy", "src", "tests", "examples") in full
    assert (
        "uv",
        "run",
        "pytest",
        "tests",
        "--cov=demo",
        "--cov-report=term-missing",
        "--cov-fail-under=95",
    ) in full


def test_validation_commands_for_minimal_profile_run_policy_check_only(tmp_path: Path) -> None:
    """Minimal projects do not require package toolchain validation commands."""
    project_dir = _generated_project(tmp_path, profile="minimal")
    config = load_generated_project_config(project_dir)

    assert validation_commands(config, quick=True) == (("scaffold-guard", "check"),)
    assert validation_commands(config, quick=False) == (("scaffold-guard", "check"),)


def test_validate_quick_json_stops_on_first_failing_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JSON validation reports executed commands and stops at the first failure."""
    project_dir = _generated_project(tmp_path)
    calls: list[tuple[str, ...]] = []

    def fake_run_command(command: tuple[str, ...], *, cwd: Path, capture: bool) -> CommandStatus:
        assert cwd == project_dir
        assert capture
        calls.append(command)
        if command == ("uv", "run", "ruff", "check", "."):
            return CommandStatus(command=command, exit_code=COMMAND_FAILED, stderr="ruff failed")
        return CommandStatus(command=command, exit_code=SUCCESS)

    monkeypatch.setattr(validation, "_run_command", fake_run_command)

    result = CliRunner().invoke(
        app,
        ["validate", "--path", str(project_dir), "--quick", "--json"],
    )

    payload = cast("dict[str, object]", json.loads(result.output))
    commands = cast("list[dict[str, object]]", payload["commands"])

    assert result.exit_code == COMMAND_FAILED
    assert payload["ok"] is False
    assert [command["command"] for command in commands] == [
        "uv run ruff format --check .",
        "uv run ruff check .",
    ]
    assert commands[1]["stderr"] == "ruff failed"
    assert calls == [
        ("uv", "run", "ruff", "format", "--check", "."),
        ("uv", "run", "ruff", "check", "."),
    ]


def test_validate_quick_text_includes_scaffold_guard_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful external quick commands continue into the in-process check."""
    project_dir = _generated_project(tmp_path)
    calls: list[tuple[str, ...]] = []

    def fake_run_command(command: tuple[str, ...], *, cwd: Path, capture: bool) -> CommandStatus:
        assert cwd == project_dir
        assert not capture
        calls.append(command)
        return CommandStatus(command=command, exit_code=SUCCESS)

    monkeypatch.setattr(validation, "_run_command", fake_run_command)

    result = CliRunner().invoke(app, ["validate", "--path", str(project_dir), "--quick"])

    assert result.exit_code == SUCCESS, result.output
    assert "scaffold-guard validate: ok" in result.output
    assert "- scaffold-guard check: ok" in result.output
    assert calls == [
        ("uv", "run", "ruff", "format", "--check", "."),
        ("uv", "run", "ruff", "check", "."),
        ("uv", "run", "pytest", "tests/unit"),
    ]


def test_validate_missing_config_uses_configuration_exit_code(tmp_path: Path) -> None:
    """Validate reports generated config errors distinctly from command failures."""
    result = CliRunner().invoke(app, ["validate", "--path", str(tmp_path), "--quick"])

    assert result.exit_code == CONFIG_ERROR
    assert "Generated project config is missing" in result.output


def test_validation_runner_reports_missing_executable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation subprocess setup reports absent executables without shell fallback."""
    project_dir = _generated_project(tmp_path)

    def fake_which(name: str) -> str | None:
        assert name == "missing-tool"
        return None

    def fake_validation_commands(
        config: GeneratedProjectConfig,
        *,
        quick: bool,
    ) -> tuple[tuple[str, ...], ...]:
        assert config.package == "demo"
        assert quick
        return (("missing-tool", "--version"),)

    monkeypatch.setattr("scaffold_guard.validation.shutil.which", fake_which)
    monkeypatch.setattr(validation, "validation_commands", fake_validation_commands)

    report = validation.run_validation(project_dir, quick=True, capture=True)
    status = report.commands[0]

    assert status.exit_code == EXECUTABLE_NOT_FOUND
    assert status.stderr == "Executable not found: missing-tool"


def test_validation_runner_captures_subprocess_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The validation runner executes commands directly and preserves display text."""
    project_dir = _generated_project(tmp_path)
    command = (sys.executable, "-c", "print('ok')")

    def fake_validation_commands(
        config: GeneratedProjectConfig,
        *,
        quick: bool,
    ) -> tuple[tuple[str, ...], ...]:
        assert config.package == "demo"
        assert quick
        return (command,)

    monkeypatch.setattr(validation, "validation_commands", fake_validation_commands)

    report = validation.run_validation(project_dir, quick=True, capture=True)
    status = report.commands[0]

    assert status.ok
    assert status.command == command
    assert status.stdout == "ok\n"
    assert report.exit_code == SUCCESS


def test_validation_reports_scaffold_guard_check_configuration_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The in-process check path preserves configuration failures."""
    project_dir = _generated_project(tmp_path)

    def fake_validation_commands(
        config: GeneratedProjectConfig,
        *,
        quick: bool,
    ) -> tuple[tuple[str, ...], ...]:
        assert config.package == "demo"
        assert quick
        return (("scaffold-guard", "check"),)

    def fake_run_checks(root: Path) -> NoReturn:
        assert root == project_dir
        raise CheckConfigurationError("bad check config")

    monkeypatch.setattr(validation, "validation_commands", fake_validation_commands)
    monkeypatch.setattr(validation, "run_checks", fake_run_checks)

    report = validation.run_validation(project_dir, quick=True, capture=True)
    status = report.commands[0]

    assert report.exit_code == CONFIG_ERROR
    assert status.stderr == "bad check config"


def test_validation_reports_scaffold_guard_check_policy_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The in-process check path returns a command failure for policy findings."""
    project_dir = _generated_project(tmp_path)
    (project_dir / "AGENTS.md").unlink()

    def fake_validation_commands(
        config: GeneratedProjectConfig,
        *,
        quick: bool,
    ) -> tuple[tuple[str, ...], ...]:
        assert config.package == "demo"
        assert quick
        return (("scaffold-guard", "check"),)

    monkeypatch.setattr(validation, "validation_commands", fake_validation_commands)

    report = validation.run_validation(project_dir, quick=True, capture=True)
    status = report.commands[0]

    assert report.exit_code == COMMAND_FAILED
    assert "project-health" in status.stdout


def test_doctor_report_allows_git_repository_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A generated project can pass doctor while warning about missing git state."""
    project_dir = _generated_project(tmp_path)

    def fake_which(name: str) -> str | None:
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Doctor text mode lists successful generated-project diagnostics."""
    project_dir = _generated_project(tmp_path, agent="codex")

    def fake_which(name: str) -> str | None:
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Doctor only checks generated adapters and CI selected by config."""
    project_dir = _generated_project(tmp_path, agent="codex")
    _replace_text(
        project_dir / "scaffold-guard.toml",
        "github_actions = true",
        "github_actions = false",
    )

    def fake_which(name: str) -> str | None:
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Git repository diagnostics degrade to a warning when git is absent."""

    def fake_which(name: str) -> str | None:
        if name == "git":
            return None
        return f"/usr/bin/{name}"

    monkeypatch.setattr("scaffold_guard.doctor.shutil.which", fake_which)

    project_dir = _generated_project(tmp_path)
    report = run_doctor(project_dir)
    checks = {check.id: check for check in report.checks}

    assert checks["git-repository"].severity == "warning"
    assert not checks["git-repository"].ok


def test_doctor_allows_minimal_profile_without_package_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Minimal profile diagnostics do not require pyproject or package source."""

    def fake_which(name: str) -> str:
        return f"/usr/bin/{name}"

    async def fake_run_git(git_path: str, root: Path) -> bool:
        assert git_path == "/usr/bin/git"
        assert root == project_dir
        return True

    project_dir = _generated_project(tmp_path, profile="minimal")
    monkeypatch.setattr("scaffold_guard.doctor.shutil.which", fake_which)
    monkeypatch.setattr(doctor, "_run_git", fake_run_git)

    report = run_doctor(project_dir)
    check_ids = {check.id for check in report.checks}

    assert report.ok
    assert "package-import-directory" not in check_ids
    assert {check.id: check for check in report.checks}["pyproject"].ok


def _generated_project(
    tmp_path: Path,
    *,
    agent: AgentChoice = "all",
    profile: ProfileChoice = "package",
) -> Path:
    """Create a generated package project for Milestone 6 tests."""
    options = build_init_options(
        "demo",
        base_dir=tmp_path,
        agent=agent,
        profile=profile,
        license_name="MIT",
        python_min="3.13",
        coverage=95,
        ci="github",
        dry_run=False,
        force=False,
    )
    scaffold_package_project(options)
    return tmp_path / "demo"


def _replace_text(path: Path, old: str, new: str) -> None:
    """Replace text in a UTF-8 file."""
    path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
