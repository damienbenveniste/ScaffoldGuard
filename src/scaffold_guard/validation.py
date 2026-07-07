"""Run generated-project validation commands."""

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path

from scaffold_guard.checks.base import CheckConfigurationError
from scaffold_guard.checks.runner import run_checks
from scaffold_guard.project_config import GeneratedProjectConfig, load_generated_project_config


class ValidationError(ValueError):
    """Raised when validation cannot be configured or executed."""


@dataclass(frozen=True, slots=True)
class CommandStatus:
    """Status for one validation command."""

    command: tuple[str, ...]
    exit_code: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        """Return whether the command succeeded."""
        return self.exit_code == 0

    @property
    def command_text(self) -> str:
        """Return a shell-like command display string."""
        return " ".join(self.command)

    def to_json(self) -> dict[str, object]:
        """Return a JSON-serializable command status."""
        return {
            "command": self.command_text,
            "exit_code": self.exit_code,
            "ok": self.ok,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Validation command report."""

    path: Path
    quick: bool
    commands: tuple[CommandStatus, ...]

    @property
    def ok(self) -> bool:
        """Return whether every executed command succeeded."""
        return all(command.ok for command in self.commands)

    @property
    def exit_code(self) -> int:
        """Return the first failing command exit code, or zero."""
        for command in self.commands:
            if not command.ok:
                return command.exit_code
        return 0

    def to_json(self) -> dict[str, object]:
        """Return a JSON-serializable validation report."""
        return {
            "ok": self.ok,
            "path": str(self.path),
            "quick": self.quick,
            "commands": [command.to_json() for command in self.commands],
        }


def validation_commands(
    config: GeneratedProjectConfig, *, quick: bool
) -> tuple[tuple[str, ...], ...]:
    """Return fixed V1 validation commands for a generated project."""
    if config.profile == "minimal":
        return (("scaffold-guard", "check"),)
    if quick:
        return (
            ("uv", "run", "ruff", "format", "--check", "."),
            ("uv", "run", "ruff", "check", "."),
            ("uv", "run", "pytest", "tests/unit"),
            ("scaffold-guard", "check"),
        )
    return (
        ("uv", "run", "ruff", "format", "--check", "."),
        ("uv", "run", "ruff", "check", "."),
        ("uv", "run", "mypy", "src", "tests", "examples"),
        ("uv", "run", "pyright"),
        ("uv", "run", "mkdocs", "build", "--strict"),
        (
            "uv",
            "run",
            "pytest",
            "tests",
            f"--cov={config.package}",
            "--cov-report=term-missing",
            f"--cov-fail-under={config.coverage_fail_under}",
        ),
        ("scaffold-guard", "check"),
    )


def run_validation(path: Path, *, quick: bool, capture: bool) -> ValidationReport:
    """Run generated-project validation commands."""
    config = load_generated_project_config(path)
    statuses: list[CommandStatus] = []
    for command in validation_commands(config, quick=quick):
        if command == ("scaffold-guard", "check"):
            status = _run_scaffold_guard_check(config.root)
        else:
            status = _run_command(command, cwd=config.root, capture=capture)
        statuses.append(status)
        if not status.ok:
            break
    return ValidationReport(path=config.root, quick=quick, commands=tuple(statuses))


def _run_scaffold_guard_check(root: Path) -> CommandStatus:
    """Run policy checks in process for stable CLI behavior."""
    try:
        report = run_checks(root)
    except CheckConfigurationError as exc:
        return CommandStatus(command=("scaffold-guard", "check"), exit_code=2, stderr=str(exc))
    if report.ok:
        return CommandStatus(command=("scaffold-guard", "check"), exit_code=0)
    return CommandStatus(
        command=("scaffold-guard", "check"),
        exit_code=1,
        stdout=str(report.to_json()),
    )


def _run_command(command: tuple[str, ...], *, cwd: Path, capture: bool) -> CommandStatus:
    """Run a validation command without shell execution."""
    executable = shutil.which(command[0])
    if executable is None:
        return CommandStatus(
            command=command,
            exit_code=127,
            stderr=f"Executable not found: {command[0]}",
        )
    return asyncio.run(
        _run_process(
            (executable, *command[1:]),
            display_command=command,
            cwd=cwd,
            capture=capture,
        )
    )


async def _run_process(
    command: tuple[str, ...],
    *,
    display_command: tuple[str, ...],
    cwd: Path,
    capture: bool,
) -> CommandStatus:
    """Run one validation subprocess."""
    stdout_target = asyncio.subprocess.PIPE if capture else None
    stderr_target = asyncio.subprocess.PIPE if capture else None
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        stdout=stdout_target,
        stderr=stderr_target,
    )
    stdout, stderr = await process.communicate()
    return CommandStatus(
        command=display_command,
        exit_code=process.returncode or 0,
        stdout=(stdout or b"").decode("utf-8", errors="replace"),
        stderr=(stderr or b"").decode("utf-8", errors="replace"),
    )
