"""Command line interface for scaffold-guard."""

import json
from contextvars import ContextVar
from enum import StrEnum
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from scaffold_guard import __version__
from scaffold_guard.checks.base import CheckConfigurationError, CheckReport
from scaffold_guard.checks.runner import run_checks
from scaffold_guard.compile_rules import CompileRulesSummary, compile_rules
from scaffold_guard.diffing import DiffInspectionError, DiffReport, inspect_diff
from scaffold_guard.doctor import DoctorReport, run_doctor
from scaffold_guard.models import ScaffoldSummary
from scaffold_guard.project_config import ProjectConfigError
from scaffold_guard.scaffold import (
    build_init_options,
    normalize_project_name,
    scaffold_package_project,
    with_quality_tools,
)
from scaffold_guard.validation import ValidationError, ValidationReport, run_validation


class AgentOption(StrEnum):
    """Supported generated-project agent adapter selections."""

    CODEX = "codex"
    CLAUDE = "claude"
    CURSOR = "cursor"
    ALL = "all"


class ProfileOption(StrEnum):
    """Supported generated-project profiles."""

    MINIMAL = "minimal"
    PACKAGE = "package"


class LicenseOption(StrEnum):
    """Supported generated-project license choices."""

    MIT = "MIT"
    APACHE_2 = "Apache-2.0"
    NONE = "none"


class CiOption(StrEnum):
    """Supported generated-project CI providers."""

    GITHUB = "github"


CHOICE_SEPARATOR = "/"
COVERAGE_MIN = 1
COVERAGE_MAX = 100
INIT_OPTION_PARAMETER_NAMES = (
    "agent",
    "profile",
    "license_name",
    "python_min",
    "coverage",
    "ci",
    "dry_run",
    "force",
)
EXPLICIT_INIT_OPTIONS_SELECTED: ContextVar[bool] = ContextVar(
    "explicit_init_options_selected",
    default=False,
)

app = typer.Typer(
    add_completion=False,
    help="Generate and inspect guarded starter repositories.",
    no_args_is_help=True,
)


def _fail(message: str) -> NoReturn:
    """Print a CLI error and exit non-zero."""
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(code=1)


def _print_init_summary(
    summary: ScaffoldSummary,
    *,
    agent: AgentOption,
    profile: ProfileOption,
    ruff: bool,
    mypy: bool,
    pyright: bool,
) -> None:
    """Print the user-facing summary after init planning or creation."""
    action = "Planned" if summary.dry_run else "Created"
    typer.echo(f"{action} ScaffoldGuard {profile.value} project: {summary.target_dir.name}")
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
    if profile == ProfileOption.PACKAGE:
        typer.echo()
        typer.echo("Python tooling:")
        typer.echo(f"  - Ruff: {'enabled' if ruff else 'disabled'}")
        typer.echo(f"  - mypy: {'enabled' if mypy else 'disabled'}")
        typer.echo(f"  - Pyright: {'enabled' if pyright else 'disabled'}")
    typer.echo()
    typer.echo("Next:")
    if summary.target_dir.resolve(strict=False) != Path.cwd().resolve(strict=False):
        typer.echo(f"  cd {summary.target_dir.name}")
    if profile == ProfileOption.PACKAGE:
        typer.echo("  uv sync --all-groups")
    typer.echo("  scaffold-guard check")
    typer.echo("  scaffold-guard validate")


def _prompt_init_name(default: str | None) -> str:
    """Prompt for a project name and validate it before continuing."""
    while True:
        if default is None or default.strip() == ".":
            name = str(
                typer.prompt(
                    "Project name (Enter for current directory)",
                    default="",
                    show_default=False,
                )
            )
        else:
            name = str(typer.prompt("Project name", default=default))
        if name.strip() == "":
            name = "."
        try:
            if name.strip() == ".":
                normalize_project_name(Path.cwd().name)
            else:
                normalize_project_name(name)
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            continue
        return name


def _prompt_choice(label: str, *, choices: tuple[str, ...], default: str) -> str:
    """Prompt until the user selects one of the provided choices."""
    choices_by_lowercase = {choice.lower(): choice for choice in choices}
    prompt_label = f"{label} ({CHOICE_SEPARATOR.join(choices)})"
    while True:
        answer = str(typer.prompt(prompt_label, default=default)).strip()
        choice = choices_by_lowercase.get(answer.lower())
        if choice is not None:
            return choice
        typer.echo(f"Choose one of: {', '.join(choices)}", err=True)


def _prompt_text(label: str, *, default: str) -> str:
    """Prompt for a non-empty text value."""
    while True:
        answer = str(typer.prompt(label, default=default)).strip()
        if answer:
            return answer
        typer.echo("Value cannot be empty.", err=True)


def _prompt_coverage(default: int) -> int:
    """Prompt for a coverage floor between 1 and 100."""
    while True:
        answer = str(typer.prompt("Coverage floor (1-100)", default=str(default))).strip()
        try:
            coverage = int(answer)
        except ValueError:
            typer.echo("Coverage floor must be an integer.", err=True)
            continue
        if COVERAGE_MIN <= coverage <= COVERAGE_MAX:
            return coverage
        typer.echo(
            f"Coverage floor must be between {COVERAGE_MIN} and {COVERAGE_MAX}.",
            err=True,
        )


def _prompt_enabled(label: str, *, default: bool) -> bool:
    """Prompt for an enabled/disabled feature selection."""
    answer = _prompt_choice(
        label,
        choices=("yes", "no"),
        default="yes" if default else "no",
    )
    return answer == "yes"


def _prompt_init_options(
    *,
    name: str | None,
    agent: AgentOption,
    profile: ProfileOption,
    license_name: LicenseOption,
    python_min: str,
    coverage: int,
    ci: CiOption,
) -> tuple[str, AgentOption, ProfileOption, LicenseOption, str, int, CiOption, bool, bool, bool]:
    """Prompt for init options while preserving current flag defaults."""
    typer.echo("ScaffoldGuard guided setup")
    typer.echo()
    prompted_name = _prompt_init_name(name)
    prompted_agent = AgentOption(
        _prompt_choice(
            "Agent adapters",
            choices=tuple(option.value for option in AgentOption),
            default=agent.value,
        )
    )
    prompted_profile = ProfileOption(
        _prompt_choice(
            "Project profile",
            choices=tuple(option.value for option in ProfileOption),
            default=profile.value,
        )
    )
    prompted_license = LicenseOption(
        _prompt_choice(
            "License",
            choices=tuple(option.value for option in LicenseOption),
            default=license_name.value,
        )
    )
    prompted_python_min = python_min
    prompted_coverage = coverage
    prompted_ruff = True
    prompted_mypy = True
    prompted_pyright = True
    if prompted_profile == ProfileOption.PACKAGE:
        prompted_python_min = _prompt_text("Minimum Python version", default=python_min)
        prompted_coverage = _prompt_coverage(coverage)
        prompted_ruff = _prompt_enabled("Use Ruff for formatting and linting", default=True)
        prompted_mypy = _prompt_enabled("Use mypy for type checking", default=True)
        prompted_pyright = _prompt_enabled("Use Pyright for type checking", default=True)
    prompted_ci = CiOption(
        _prompt_choice(
            "CI provider",
            choices=tuple(option.value for option in CiOption),
            default=ci.value,
        )
    )
    return (
        prompted_name,
        prompted_agent,
        prompted_profile,
        prompted_license,
        prompted_python_min,
        prompted_coverage,
        prompted_ci,
        prompted_ruff,
        prompted_mypy,
        prompted_pyright,
    )


def _capture_explicit_init_options(
    ctx: typer.Context,
    _parameter: typer.CallbackParam,
    value: str | None,
) -> str | None:
    """Record whether init behavior was selected with explicit CLI options."""
    EXPLICIT_INIT_OPTIONS_SELECTED.set(False)
    for parameter_name in INIT_OPTION_PARAMETER_NAMES:
        source = ctx.get_parameter_source(parameter_name)
        if source is not None and source.name == "COMMANDLINE":
            EXPLICIT_INIT_OPTIONS_SELECTED.set(True)
            break
    return value


def _has_explicit_init_options() -> bool:
    """Return whether init behavior was selected with explicit CLI options."""
    return EXPLICIT_INIT_OPTIONS_SELECTED.get()


def _should_prompt_init(*, name: str | None, guided: bool) -> bool:
    """Return whether init should start the guided prompt flow."""
    if guided or name is None:
        return True
    return name.strip() == "." and not _has_explicit_init_options()


def _print_check_report(report: CheckReport) -> None:
    """Print a human-readable check report."""
    typer.echo(f"scaffold-guard check: {'ok' if report.ok else 'failed'}")
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
    typer.echo(f"scaffold-guard validate: {'ok' if report.ok else 'failed'}")
    typer.echo(f"path: {report.path}")
    for status in report.commands:
        outcome = "ok" if status.ok else f"failed ({status.exit_code})"
        typer.echo(f"- {status.command_text}: {outcome}")


def _print_doctor_report(report: DoctorReport) -> None:
    """Print doctor diagnostics."""
    typer.echo(f"scaffold-guard doctor: {'ok' if report.ok else 'failed'}")
    typer.echo(f"path: {report.path}")
    for check in report.checks:
        outcome = "ok" if check.ok else check.severity
        typer.echo(f"- {check.id}: {outcome} - {check.message}")


@app.command("version")
def version_command() -> None:
    """Print the installed scaffold-guard version."""
    typer.echo(__version__)


@app.command("init")
def init_command(
    name: Annotated[
        str | None,
        typer.Argument(
            help="Project directory name to create. Omit to use guided setup.",
            callback=_capture_explicit_init_options,
        ),
    ] = None,
    agent: Annotated[
        AgentOption,
        typer.Option("--agent", help="Agent adapter files to generate."),
    ] = AgentOption.ALL,
    profile: Annotated[
        ProfileOption,
        typer.Option("--profile", help="Generated project profile."),
    ] = ProfileOption.MINIMAL,
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
    guided: Annotated[
        bool,
        typer.Option("--guided", help="Prompt for init options even when NAME is provided."),
    ] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show planned files only.")] = False,
    force: Annotated[bool, typer.Option("--force", help="Overwrite generated files.")] = False,
) -> None:
    """Create a new ScaffoldGuard project."""
    ruff = True
    mypy = True
    pyright = True
    if _should_prompt_init(name=name, guided=guided):
        (
            name,
            agent,
            profile,
            license_name,
            python_min,
            coverage,
            ci,
            ruff,
            mypy,
            pyright,
        ) = _prompt_init_options(
            name=name,
            agent=agent,
            profile=profile,
            license_name=license_name,
            python_min=python_min,
            coverage=coverage,
            ci=ci,
        )
    if name is None:
        _fail("Project name is required.")
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
        options = with_quality_tools(options, ruff=ruff, mypy=mypy, pyright=pyright)
        summary = scaffold_package_project(options)
    except (FileExistsError, NotADirectoryError, ValueError) as exc:
        _fail(str(exc))
    _print_init_summary(
        summary, agent=agent, profile=profile, ruff=ruff, mypy=mypy, pyright=pyright
    )


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
        typer.Option(
            "--path",
            help="Project root containing scaffold-guard.toml.",
            resolve_path=True,
        ),
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
