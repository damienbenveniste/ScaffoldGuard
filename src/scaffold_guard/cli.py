"""Command line interface for scaffold-guard."""

import json
from contextvars import ContextVar
from dataclasses import dataclass
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
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    MONOREPO = "monorepo"


class LicenseOption(StrEnum):
    """Supported generated-project license choices."""

    MIT = "MIT"
    APACHE_2 = "Apache-2.0"
    NONE = "none"


class CiOption(StrEnum):
    """Supported generated-project CI providers."""

    GITHUB = "github"
    GITLAB = "gitlab"


class RuffSetupOption(StrEnum):
    """Supported generated Python Ruff linting choices."""

    STRICT = "strict"
    STANDARD = "standard"
    OFF = "off"


class PythonTypecheckModeOption(StrEnum):
    """Supported generated Python type-checking strictness choices."""

    STRICT = "strict"
    STANDARD = "standard"
    OFF = "off"


class PythonTypecheckerOption(StrEnum):
    """Supported generated Python type checker selections."""

    MYPY_PYRIGHT = "mypy+pyright"
    MYPY = "mypy"
    PYRIGHT = "pyright"


class TypeScriptModeOption(StrEnum):
    """Supported generated TypeScript compiler strictness choices."""

    STRICT = "strict"
    STANDARD = "standard"


class TypeScriptLintOption(StrEnum):
    """Supported generated TypeScript formatting and linting choices."""

    BIOME = "biome"
    OFF = "off"


class TypeScriptTestOption(StrEnum):
    """Supported generated TypeScript test runner choices."""

    VITEST = "vitest"
    OFF = "off"


@dataclass(frozen=True, slots=True)
class PromptedInitOptions:
    """Options collected from guided init prompts."""

    name: str
    agent: AgentOption
    profile: ProfileOption
    license_name: LicenseOption
    python_min: str
    coverage: int
    ci: CiOption
    ruff: bool
    mypy: bool
    pyright: bool
    ruff_setup: RuffSetupOption
    python_typecheck_mode: PythonTypecheckModeOption
    python_typechecker: PythonTypecheckerOption
    typescript_strict: bool
    biome: bool
    vitest: bool


@dataclass(frozen=True, slots=True)
class InitPromptDefaults:
    """Default values used by guided init prompts."""

    name: str | None
    agent: AgentOption
    profile: ProfileOption
    license_name: LicenseOption
    python_min: str
    coverage: int
    ci: CiOption
    ruff_setup: RuffSetupOption
    python_typecheck_mode: PythonTypecheckModeOption
    python_typechecker: PythonTypecheckerOption
    typescript_mode: TypeScriptModeOption
    typescript_lint: TypeScriptLintOption
    typescript_test: TypeScriptTestOption


CHOICE_SEPARATOR = "/"
COVERAGE_MIN = 1
COVERAGE_MAX = 100
PROFILE_DESCRIPTIONS = (
    ("minimal", "guardrails only; no Python or TypeScript source scaffold"),
    ("python", "Python package scaffold with src/, tests/, docs/, and uv"),
    ("typescript", "TypeScript package scaffold with npm and configurable tooling"),
    ("monorepo", "Python + TypeScript workspaces under packages/"),
)
PROFILE_CHOICES = tuple(option.value for option in ProfileOption)
INIT_OPTION_PARAMETER_NAMES = (
    "agent",
    "profile",
    "license_name",
    "python_min",
    "coverage",
    "ci",
    "ruff_setup",
    "python_typecheck_mode",
    "python_typechecker",
    "typescript_mode",
    "typescript_lint",
    "typescript_test",
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
    ci: CiOption,
    ruff_setup: RuffSetupOption,
    python_typecheck_mode: PythonTypecheckModeOption,
    python_typechecker: PythonTypecheckerOption,
    typescript_strict: bool,
    biome: bool,
    vitest: bool,
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
    if profile in {ProfileOption.PYTHON, ProfileOption.MONOREPO}:
        ruff = _ruff_enabled(ruff_setup)
        mypy, pyright = _python_typecheck_enabled(python_typecheck_mode, python_typechecker)
        typecheck_display = (
            "disabled"
            if python_typecheck_mode == PythonTypecheckModeOption.OFF
            else python_typecheck_mode.value
        )
        typer.echo()
        typer.echo("Python tooling:")
        typer.echo(f"  - Ruff: {ruff_setup.value if ruff else 'disabled'}")
        typer.echo(f"  - Type checking: {typecheck_display}")
        if python_typecheck_mode != PythonTypecheckModeOption.OFF:
            typer.echo(f"  - Typechecker: {python_typechecker.value}")
        typer.echo(f"  - mypy: {'enabled' if mypy else 'disabled'}")
        typer.echo(f"  - Pyright: {'enabled' if pyright else 'disabled'}")
    if profile in {ProfileOption.TYPESCRIPT, ProfileOption.MONOREPO}:
        typer.echo()
        typer.echo("TypeScript tooling:")
        typer.echo(f"  - TypeScript compiler: {'strict' if typescript_strict else 'standard'}")
        typer.echo(f"  - Biome: {'enabled' if biome else 'disabled'}")
        typer.echo(f"  - Vitest: {'enabled' if vitest else 'disabled'}")
    typer.echo()
    typer.echo("CI:")
    typer.echo(f"  - {ci.value}")
    typer.echo()
    typer.echo("Next:")
    if summary.target_dir.resolve(strict=False) != Path.cwd().resolve(strict=False):
        typer.echo(f"  cd {summary.target_dir.name}")
    if profile in {ProfileOption.PYTHON, ProfileOption.MONOREPO}:
        typer.echo("  uv sync --all-groups")
    if profile in {ProfileOption.TYPESCRIPT, ProfileOption.MONOREPO}:
        typer.echo("  npm install")
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


def _profile_callback(value: str | None) -> str:
    """Validate and normalize `--profile`, preserving the legacy package alias."""
    if value is None:
        return ProfileOption.MINIMAL.value
    normalized = value.strip().lower()
    if normalized == "package":
        return ProfileOption.PYTHON.value
    if normalized in PROFILE_CHOICES:
        return normalized
    choices = ", ".join(PROFILE_CHOICES)
    raise typer.BadParameter(f"choose one of: {choices}")


def _prompt_text(label: str, *, default: str) -> str:
    """Prompt for a non-empty text value."""
    while True:
        answer = str(typer.prompt(label, default=default)).strip()
        if answer:
            return answer
        typer.echo("Value cannot be empty.", err=True)


def _prompt_coverage(default: int) -> int:
    """Prompt for a test coverage floor between 1 and 100."""
    while True:
        answer = str(typer.prompt("Test coverage floor (1-100)", default=str(default))).strip()
        try:
            coverage = int(answer)
        except ValueError:
            typer.echo("Test coverage floor must be an integer.", err=True)
            continue
        if COVERAGE_MIN <= coverage <= COVERAGE_MAX:
            return coverage
        typer.echo(
            f"Test coverage floor must be between {COVERAGE_MIN} and {COVERAGE_MAX}.",
            err=True,
        )


def _ruff_enabled(option: RuffSetupOption) -> bool:
    """Return whether generated Python projects should include Ruff."""
    return option != RuffSetupOption.OFF


def _python_typecheck_enabled(
    mode: PythonTypecheckModeOption,
    checker: PythonTypecheckerOption,
) -> tuple[bool, bool]:
    """Return mypy and Pyright enablement for a Python type-checking choice."""
    if mode == PythonTypecheckModeOption.OFF:
        return False, False
    return (
        checker in {PythonTypecheckerOption.MYPY_PYRIGHT, PythonTypecheckerOption.MYPY},
        checker in {PythonTypecheckerOption.MYPY_PYRIGHT, PythonTypecheckerOption.PYRIGHT},
    )


def _typescript_strict_enabled(option: TypeScriptModeOption) -> bool:
    """Return whether generated TypeScript should use strict compiler options."""
    return option == TypeScriptModeOption.STRICT


def _biome_enabled(option: TypeScriptLintOption) -> bool:
    """Return whether generated TypeScript projects should include Biome."""
    return option == TypeScriptLintOption.BIOME


def _vitest_enabled(option: TypeScriptTestOption) -> bool:
    """Return whether generated TypeScript projects should include Vitest."""
    return option == TypeScriptTestOption.VITEST


def _print_profile_descriptions() -> None:
    """Print short descriptions for guided profile choices."""
    typer.echo("Project profiles:")
    for profile_name, description in PROFILE_DESCRIPTIONS:
        typer.echo(f"  - {profile_name}: {description}")
    typer.echo()


def _prompt_init_options(defaults: InitPromptDefaults) -> PromptedInitOptions:
    """Prompt for init options while preserving current flag defaults."""
    typer.echo("ScaffoldGuard guided setup")
    typer.echo()
    prompted_name = _prompt_init_name(defaults.name)
    prompted_agent = AgentOption(
        _prompt_choice(
            "Agent adapters",
            choices=tuple(option.value for option in AgentOption),
            default=defaults.agent.value,
        )
    )
    _print_profile_descriptions()
    prompted_profile = ProfileOption(
        _prompt_choice(
            "Project profile",
            choices=PROFILE_CHOICES,
            default=defaults.profile.value,
        )
    )
    prompted_license = LicenseOption(
        _prompt_choice(
            "License",
            choices=tuple(option.value for option in LicenseOption),
            default=defaults.license_name.value,
        )
    )
    prompted_python_min = defaults.python_min
    prompted_coverage = defaults.coverage
    prompted_ruff = False
    prompted_mypy = False
    prompted_pyright = False
    prompted_ruff_setup = RuffSetupOption.OFF
    prompted_python_typecheck_mode = PythonTypecheckModeOption.OFF
    prompted_python_typechecker = defaults.python_typechecker
    prompted_typescript_strict = True
    prompted_biome = False
    prompted_vitest = False
    if prompted_profile in {ProfileOption.PYTHON, ProfileOption.MONOREPO}:
        prompted_python_min = _prompt_text("Minimum Python version", default=defaults.python_min)
        prompted_ruff_setup = RuffSetupOption(
            _prompt_choice(
                "Ruff strictness",
                choices=tuple(option.value for option in RuffSetupOption),
                default=defaults.ruff_setup.value,
            )
        )
        prompted_python_typecheck_mode = PythonTypecheckModeOption(
            _prompt_choice(
                "Python type-check strictness",
                choices=tuple(option.value for option in PythonTypecheckModeOption),
                default=defaults.python_typecheck_mode.value,
            )
        )
        if prompted_python_typecheck_mode != PythonTypecheckModeOption.OFF:
            prompted_python_typechecker = PythonTypecheckerOption(
                _prompt_choice(
                    "Python typechecker",
                    choices=tuple(option.value for option in PythonTypecheckerOption),
                    default=defaults.python_typechecker.value,
                )
            )
        prompted_ruff = _ruff_enabled(prompted_ruff_setup)
        prompted_mypy, prompted_pyright = _python_typecheck_enabled(
            prompted_python_typecheck_mode,
            prompted_python_typechecker,
        )
    if prompted_profile in {ProfileOption.TYPESCRIPT, ProfileOption.MONOREPO}:
        prompted_typescript_mode = TypeScriptModeOption(
            _prompt_choice(
                "TypeScript mode",
                choices=tuple(option.value for option in TypeScriptModeOption),
                default=defaults.typescript_mode.value,
            )
        )
        prompted_typescript_lint = TypeScriptLintOption(
            _prompt_choice(
                "TypeScript formatter/linter",
                choices=tuple(option.value for option in TypeScriptLintOption),
                default=defaults.typescript_lint.value,
            )
        )
        prompted_typescript_test = TypeScriptTestOption(
            _prompt_choice(
                "TypeScript test runner",
                choices=tuple(option.value for option in TypeScriptTestOption),
                default=defaults.typescript_test.value,
            )
        )
        prompted_typescript_strict = _typescript_strict_enabled(prompted_typescript_mode)
        prompted_biome = _biome_enabled(prompted_typescript_lint)
        prompted_vitest = _vitest_enabled(prompted_typescript_test)
    if prompted_profile in {ProfileOption.PYTHON, ProfileOption.MONOREPO} or prompted_vitest:
        prompted_coverage = _prompt_coverage(defaults.coverage)
    prompted_ci = CiOption(
        _prompt_choice(
            "CI provider",
            choices=tuple(option.value for option in CiOption),
            default=defaults.ci.value,
        )
    )
    return PromptedInitOptions(
        name=prompted_name,
        agent=prompted_agent,
        profile=prompted_profile,
        license_name=prompted_license,
        python_min=prompted_python_min,
        coverage=prompted_coverage,
        ci=prompted_ci,
        ruff=prompted_ruff,
        mypy=prompted_mypy,
        pyright=prompted_pyright,
        ruff_setup=prompted_ruff_setup,
        python_typecheck_mode=prompted_python_typecheck_mode,
        python_typechecker=prompted_python_typechecker,
        typescript_strict=prompted_typescript_strict,
        biome=prompted_biome,
        vitest=prompted_vitest,
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
def init_command(  # noqa: PLR0913 - Typer exposes one parameter per public CLI option.
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
        str,
        typer.Option(
            "--profile",
            callback=_profile_callback,
            help=(
                "Generated project profile: minimal guardrails only, no source scaffold; "
                "python Python package scaffold; typescript TypeScript package scaffold; "
                "monorepo Python + TypeScript workspaces. Tool setup is configured with "
                "--ruff, --python-typecheck, --python-typechecker, --typescript-mode, "
                "--typescript-lint, and --typescript-test."
            ),
        ),
    ] = ProfileOption.MINIMAL.value,
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
        typer.Option("--coverage", min=1, max=100, help="Generated project test coverage floor."),
    ] = 95,
    ci: Annotated[CiOption, typer.Option("--ci", help="Generated CI provider.")] = CiOption.GITHUB,
    ruff_setup: Annotated[
        RuffSetupOption,
        typer.Option("--ruff", help="Generated Python Ruff strictness."),
    ] = RuffSetupOption.STRICT,
    python_typecheck_mode: Annotated[
        PythonTypecheckModeOption,
        typer.Option("--python-typecheck", help="Generated Python type-checking strictness."),
    ] = PythonTypecheckModeOption.STRICT,
    python_typechecker: Annotated[
        PythonTypecheckerOption,
        typer.Option("--python-typechecker", help="Generated Python typechecker selection."),
    ] = PythonTypecheckerOption.MYPY_PYRIGHT,
    typescript_mode: Annotated[
        TypeScriptModeOption,
        typer.Option("--typescript-mode", help="Generated TypeScript compiler mode."),
    ] = TypeScriptModeOption.STRICT,
    typescript_lint: Annotated[
        TypeScriptLintOption,
        typer.Option("--typescript-lint", help="Generated TypeScript formatter/linter setup."),
    ] = TypeScriptLintOption.BIOME,
    typescript_test: Annotated[
        TypeScriptTestOption,
        typer.Option("--typescript-test", help="Generated TypeScript test runner setup."),
    ] = TypeScriptTestOption.VITEST,
    guided: Annotated[
        bool,
        typer.Option("--guided", help="Prompt for init options even when NAME is provided."),
    ] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show planned files only.")] = False,
    force: Annotated[bool, typer.Option("--force", help="Overwrite generated files.")] = False,
) -> None:
    """Create a new ScaffoldGuard project."""
    profile_option = ProfileOption(profile)
    ruff = _ruff_enabled(ruff_setup)
    mypy, pyright = _python_typecheck_enabled(python_typecheck_mode, python_typechecker)
    typescript_strict = _typescript_strict_enabled(typescript_mode)
    biome = _biome_enabled(typescript_lint)
    vitest = _vitest_enabled(typescript_test)
    if _should_prompt_init(name=name, guided=guided):
        prompted_options = _prompt_init_options(
            InitPromptDefaults(
                name=name,
                agent=agent,
                profile=profile_option,
                license_name=license_name,
                python_min=python_min,
                coverage=coverage,
                ci=ci,
                ruff_setup=ruff_setup,
                python_typecheck_mode=python_typecheck_mode,
                python_typechecker=python_typechecker,
                typescript_mode=typescript_mode,
                typescript_lint=typescript_lint,
                typescript_test=typescript_test,
            )
        )
        name = prompted_options.name
        agent = prompted_options.agent
        profile_option = prompted_options.profile
        license_name = prompted_options.license_name
        python_min = prompted_options.python_min
        coverage = prompted_options.coverage
        ci = prompted_options.ci
        ruff = prompted_options.ruff
        mypy = prompted_options.mypy
        pyright = prompted_options.pyright
        ruff_setup = prompted_options.ruff_setup
        python_typecheck_mode = prompted_options.python_typecheck_mode
        python_typechecker = prompted_options.python_typechecker
        typescript_strict = prompted_options.typescript_strict
        biome = prompted_options.biome
        vitest = prompted_options.vitest
    if profile_option not in {ProfileOption.PYTHON, ProfileOption.MONOREPO}:
        ruff = False
        mypy = False
        pyright = False
        ruff_setup = RuffSetupOption.OFF
        python_typecheck_mode = PythonTypecheckModeOption.OFF
    if profile_option not in {ProfileOption.TYPESCRIPT, ProfileOption.MONOREPO}:
        biome = False
        vitest = False
    if name is None:
        _fail("Project name is required.")
    try:
        options = build_init_options(
            name,
            base_dir=Path.cwd(),
            agent=agent.value,
            profile=profile_option.value,
            license_name=license_name.value,
            python_min=python_min,
            coverage=coverage,
            ci=ci.value,
            dry_run=dry_run,
            force=force,
        )
        options = with_quality_tools(
            options,
            ruff=ruff,
            mypy=mypy,
            pyright=pyright,
            ruff_mode=ruff_setup.value,
            python_typecheck_mode=python_typecheck_mode.value,
            python_typechecker=python_typechecker.value,
            typescript_strict=typescript_strict,
            biome=biome,
            vitest=vitest,
        )
        summary = scaffold_package_project(options)
    except (FileExistsError, NotADirectoryError, ValueError) as exc:
        _fail(str(exc))
    _print_init_summary(
        summary,
        agent=agent,
        profile=profile_option,
        ci=ci,
        ruff_setup=ruff_setup,
        python_typecheck_mode=python_typecheck_mode,
        python_typechecker=python_typechecker,
        typescript_strict=typescript_strict,
        biome=biome,
        vitest=vitest,
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
