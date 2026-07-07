"""Tests for generated project validation commands."""

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn, cast

import pytest
from typer.testing import CliRunner

from scaffold_guard import validation
from scaffold_guard.checks.base import CheckConfigurationError
from scaffold_guard.cli import app
from scaffold_guard.project_config import GeneratedProjectConfig, load_generated_project_config
from scaffold_guard.validation import CommandStatus, validation_commands

SUCCESS = 0
COMMAND_FAILED = 1
CONFIG_ERROR = 2
EXECUTABLE_NOT_FOUND = 127


def test_validation_commands_are_fixed_for_quick_and_full_profiles(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Validation command planning uses project package and coverage settings."""
    project_dir = generated_project(tmp_path)
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


def test_validation_commands_for_minimal_profile_run_policy_check_only(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Minimal projects do not require package toolchain validation commands."""
    project_dir = generated_project(tmp_path, profile="minimal")
    config = load_generated_project_config(project_dir)

    assert validation_commands(config, quick=True) == (("scaffold-guard", "check"),)
    assert validation_commands(config, quick=False) == (("scaffold-guard", "check"),)


def test_validate_quick_json_stops_on_first_failing_command(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JSON validation reports executed commands and stops at the first failure."""
    project_dir = generated_project(tmp_path)
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
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful external quick commands continue into the in-process check."""
    project_dir = generated_project(tmp_path)
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
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation subprocess setup reports absent executables without shell fallback."""
    project_dir = generated_project(tmp_path)

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
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The validation runner executes commands directly and preserves display text."""
    project_dir = generated_project(tmp_path)
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
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The in-process check path preserves configuration failures."""
    project_dir = generated_project(tmp_path)

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
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The in-process check path returns a command failure for policy findings."""
    project_dir = generated_project(tmp_path)
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
