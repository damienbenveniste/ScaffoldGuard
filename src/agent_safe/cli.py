"""Command line interface for agent-safe-python."""

import json
from enum import StrEnum
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from agent_safe import __version__
from agent_safe.checks.base import CheckConfigurationError, CheckReport
from agent_safe.checks.runner import run_checks
from agent_safe.compile_rules import CompileRulesSummary, compile_rules
from agent_safe.diffing import DiffInspectionError, DiffReport, inspect_diff
from agent_safe.doctor import DoctorReport, run_doctor
from agent_safe.models import ScaffoldSummary
from agent_safe.project_config import ProjectConfigError
from agent_safe.scaffold import build_init_options, scaffold_package_project
from agent_safe.validation import ValidationError, ValidationReport, run_validation


class AgentOption(StrEnum):
    """Supported generated-project agent adapter selections."""

    CODEX = "codex"
    CLAUDE = "claude"
    CURSOR = "cursor"
    ALL = "all"


class ProfileOption(StrEnum):
    """Supported generated-project profiles."""

    PACKAGE = "package"


class LicenseOption(StrEnum):
    """Supported generated-project license choices."""

    MIT = "MIT"
    APACHE_2 = "Apache-2.0"
    NONE = "none"


class CiOption(StrEnum):
    """Supported generated-project CI providers."""

    GITHUB = "github"


app = typer.Typer(
    add_completion=False,
    help="Generate and inspect agent-safe Python starter repositories.",
    no_args_is_help=True,
)


def _fail(message: str) -> NoReturn:
    """Print a CLI error and exit non-zero."""
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(code=1)


def _print_init_summary(summary: ScaffoldSummary, *, agent: AgentOption) -> None:
    """Print the user-facing summary after init planning or creation."""
    action = "Planned" if summary.dry_run else "Created"
    typer.echo(f"{action} agent-safe Python project: {summary.target_dir.name}")
    typer.echo()
    typer.echo("Files:")
    for file_path in summary.files:
        typer.echo(f"  - {file_path.as_posix()}")
    typer.echo()
    typer.echo("Agent adapters:")
    typer.echo("  - Codex: AGENTS.md")
    if agent in {AgentOption.CLAUDE, AgentOption.ALL}:
        typer.echo("  - Claude Code: CLAUDE.md + .claude/rules/")
    if agent in {AgentOption.CURSOR, AgentOption.ALL}:
        typer.echo("  - Cursor: .cursor/rules/*.mdc + AGENTS.md")
    typer.echo()
    typer.echo("Next:")
    typer.echo(f"  cd {summary.target_dir.name}")
    typer.echo("  uv sync --all-groups")
    typer.echo("  uv run agent-safe check")
    typer.echo("  uv run agent-safe validate")


def _print_check_report(report: CheckReport) -> None:
    """Print a human-readable check report."""
    typer.echo(f"agent-safe check: {'ok' if report.ok else 'failed'}")
    typer.echo(f"path: {report.path}")
    for check in report.checks:
        status = "ok" if check.ok else "failed"
        typer.echo(f"- {check.id}: {status}")
        for finding in check.findings:
            location = finding.path
            if finding.line > 0:
                location = f"{location}:{finding.line}"
            typer.echo(f"  [{finding.severity}] {finding.code} {location} - {finding.message}")


def _print_diff_report(report: DiffReport) -> None:
    """Print a human-readable diff impact report."""
    typer.echo("Diff impact summary")
    typer.echo()
    typer.echo("Changed areas:")
    if report.changed_areas:
        for area in report.changed_areas:
            typer.echo(f"  - {area.label}: {area.path.as_posix()}")
    else:
        typer.echo("  - none")
    typer.echo()
    typer.echo("Required validation:")
    if report.required_validation:
        for command in report.required_validation:
            typer.echo(f"  - {command}")
    else:
        typer.echo("  - none")
    typer.echo()
    typer.echo("Required evidence before claiming done:")
    if report.required_evidence:
        for evidence in report.required_evidence:
            typer.echo(f"  - {evidence}")
    else:
        typer.echo("  - none")
    if report.warnings:
        typer.echo()
        typer.echo("Warnings:")
        for warning in report.warnings:
            typer.echo(f"  - {warning}")


def _print_compile_rules_summary(summary: CompileRulesSummary) -> None:
    """Print a compile-rules summary."""
    action = "Planned" if summary.dry_run else "Regenerated"
    typer.echo(f"{action} agent instruction files: {summary.target_dir}")
    for file_path in summary.files:
        typer.echo(f"  - {file_path.as_posix()}")


def _print_validation_report(report: ValidationReport) -> None:
    """Print a validation command summary."""
    typer.echo(f"agent-safe validate: {'ok' if report.ok else 'failed'}")
    typer.echo(f"path: {report.path}")
    for status in report.commands:
        outcome = "ok" if status.ok else f"failed ({status.exit_code})"
        typer.echo(f"- {status.command_text}: {outcome}")


def _print_doctor_report(report: DoctorReport) -> None:
    """Print doctor diagnostics."""
    typer.echo(f"agent-safe doctor: {'ok' if report.ok else 'failed'}")
    typer.echo(f"path: {report.path}")
    for check in report.checks:
        outcome = "ok" if check.ok else check.severity
        typer.echo(f"- {check.id}: {outcome} - {check.message}")


@app.command("version")
def version_command() -> None:
    """Print the installed agent-safe-python version."""
    typer.echo(__version__)


@app.command("init")
def init_command(
    name: Annotated[str, typer.Argument(help="Project directory name to create.")],
    agent: Annotated[
        AgentOption,
        typer.Option("--agent", help="Agent adapter files to generate."),
    ] = AgentOption.ALL,
    profile: Annotated[
        ProfileOption,
        typer.Option("--profile", help="Generated project profile."),
    ] = ProfileOption.PACKAGE,
    license_name: Annotated[
        LicenseOption,
        typer.Option("--license", help="Generated project license."),
    ] = LicenseOption.MIT,
    python_min: Annotated[
        str,
        typer.Option(
            "--python-min",
            help="Minimum Python version for the generated project.",
        ),
    ] = "3.13",
    coverage: Annotated[
        int,
        typer.Option("--coverage", min=1, max=100, help="Generated project coverage floor."),
    ] = 95,
    ci: Annotated[CiOption, typer.Option("--ci", help="Generated CI provider.")] = CiOption.GITHUB,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show planned files only.")] = False,
    force: Annotated[bool, typer.Option("--force", help="Overwrite generated files.")] = False,
) -> None:
    """Create a new agent-safe Python project."""
    try:
        options = build_init_options(
            name,
            base_dir=Path.cwd(),
            agent=agent.value,
            profile=profile.value,
            license_name=license_name.value,
            python_min=python_min,
            coverage=coverage,
            ci=ci.value,
            dry_run=dry_run,
            force=force,
        )
        summary = scaffold_package_project(options)
    except (FileExistsError, NotADirectoryError, ValueError) as exc:
        _fail(str(exc))
    _print_init_summary(summary, agent=agent)


@app.command("check")
def check_command(
    path: Annotated[
        Path,
        typer.Option("--path", help="Project root to inspect.", resolve_path=True),
    ] = Path(),
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output.")] = False,
) -> None:
    """Run fast local policy checks."""
    try:
        report = run_checks(path)
    except CheckConfigurationError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_output:
        typer.echo(json.dumps(report.to_json(), indent=2, sort_keys=True))
    else:
        _print_check_report(report)
    if not report.ok:
        raise typer.Exit(code=1)


@app.command("inspect-diff")
def inspect_diff_command(
    path: Annotated[
        Path,
        typer.Option("--path", help="Project root to inspect.", resolve_path=True),
    ] = Path(),
    base: Annotated[str, typer.Option("--base", help="Git base revision.")] = "main",
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output.")] = False,
) -> None:
    """Report validation obligations for the current diff."""
    try:
        report = inspect_diff(path, base=base)
    except DiffInspectionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_output:
        typer.echo(json.dumps(report.to_json(), indent=2, sort_keys=True))
    else:
        _print_diff_report(report)


@app.command("validate")
def validate_command(
    path: Annotated[
        Path,
        typer.Option("--path", help="Project root to validate.", resolve_path=True),
    ] = Path(),
    quick: Annotated[bool, typer.Option("--quick", help="Run the quick validation gate.")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output.")] = False,
) -> None:
    """Run configured project validation commands."""
    try:
        report = run_validation(path, quick=quick, capture=json_output)
    except (ProjectConfigError, ValidationError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_output:
        typer.echo(json.dumps(report.to_json(), indent=2, sort_keys=True))
    else:
        _print_validation_report(report)
    if not report.ok:
        raise typer.Exit(code=report.exit_code)


@app.command("compile-rules")
def compile_rules_command(
    path: Annotated[
        Path,
        typer.Option("--path", help="Project root containing agent-safe.toml.", resolve_path=True),
    ] = Path(),
    agent: Annotated[
        AgentOption,
        typer.Option("--agent", help="Agent adapter files to compile."),
    ] = AgentOption.ALL,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show planned files only.")] = False,
    force: Annotated[bool, typer.Option("--force", help="Overwrite generated files.")] = False,
) -> None:
    """Regenerate generated agent instruction files."""
    try:
        summary = compile_rules(
            path,
            agent=agent.value,
            dry_run=dry_run,
            force=force,
        )
    except (ProjectConfigError, FileExistsError, NotADirectoryError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    _print_compile_rules_summary(summary)


@app.command("doctor")
def doctor_command(
    path: Annotated[
        Path,
        typer.Option("--path", help="Project root to inspect.", resolve_path=True),
    ] = Path(),
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output.")] = False,
) -> None:
    """Report local environment and generated-project health."""
    report = run_doctor(path)
    if json_output:
        typer.echo(json.dumps(report.to_json(), indent=2, sort_keys=True))
    else:
        _print_doctor_report(report)
    if not report.ok:
        raise typer.Exit(code=1)
