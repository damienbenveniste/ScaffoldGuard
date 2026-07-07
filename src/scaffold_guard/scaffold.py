"""Scaffold planning and file writing helpers."""

import keyword
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from scaffold_guard.adapters import adapters_for
from scaffold_guard.fs import ensure_relative_safe_path, is_within_directory, write_text_safely
from scaffold_guard.models import (
    AgentChoice,
    InitOptions,
    LicenseChoice,
    ProfileChoice,
    ScaffoldSummary,
    TemplateSpec,
)
from scaffold_guard.renderer import TemplateRenderer

PROJECT_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
SUPPORTED_PROFILES = {"minimal", "package"}

PACKAGE_TEMPLATE_SPECS = (
    TemplateSpec("package/AGENTS.md.j2", "AGENTS.md"),
    TemplateSpec("package/README.md.j2", "README.md"),
    TemplateSpec("package/LICENSE.j2", "LICENSE"),
    TemplateSpec("package/pyproject.toml.j2", "pyproject.toml"),
    TemplateSpec("package/gitignore.j2", ".gitignore"),
    TemplateSpec("package/scaffold-guard.toml.j2", "scaffold-guard.toml"),
    TemplateSpec("package/docs/index.md.j2", "docs/index.md"),
    TemplateSpec("package/examples/hello.py.j2", "examples/hello.py"),
    TemplateSpec("package/src/package/__init__.py.j2", "src/{package_name}/__init__.py"),
    TemplateSpec("package/src/package/core.py.j2", "src/{package_name}/core.py"),
    TemplateSpec("package/src/package/py.typed.j2", "src/{package_name}/py.typed"),
    TemplateSpec("package/tests/unit/test_core.py.j2", "tests/unit/test_core.py"),
    TemplateSpec(
        "package/tests/integration/test_import_package.py.j2",
        "tests/integration/test_import_package.py",
    ),
    TemplateSpec("package/github/workflows/ci.yml.j2", ".github/workflows/ci.yml"),
    TemplateSpec("package/github/workflows/docs.yml.j2", ".github/workflows/docs.yml"),
)
MINIMAL_TEMPLATE_SPECS = (
    TemplateSpec("minimal/AGENTS.md.j2", "AGENTS.md"),
    TemplateSpec("minimal/README.md.j2", "README.md"),
    TemplateSpec("package/LICENSE.j2", "LICENSE"),
    TemplateSpec("minimal/gitignore.j2", ".gitignore"),
    TemplateSpec("minimal/scaffold-guard.toml.j2", "scaffold-guard.toml"),
    TemplateSpec("minimal/github/workflows/ci.yml.j2", ".github/workflows/ci.yml"),
)


@dataclass(frozen=True, slots=True)
class RenderedFile:
    """A generated file path and its rendered text content."""

    path: Path
    content: str
    generated: bool = True


def normalize_project_name(name: str) -> tuple[str, str]:
    """Validate a requested project name and return slug plus package name."""
    stripped_name = name.strip()
    relative_name = ensure_relative_safe_path(stripped_name)
    if len(relative_name.parts) != 1:
        msg = f"Project name must be a directory name, not a path: {name}"
        raise ValueError(msg)
    if not PROJECT_NAME_PATTERN.fullmatch(stripped_name):
        msg = (
            "Project name must start with a letter and contain only letters, "
            f"numbers, '-' or '_': {name}"
        )
        raise ValueError(msg)

    project_slug = stripped_name.lower()
    package_name = project_slug.replace("-", "_")
    if not package_name.isidentifier() or keyword.iskeyword(package_name):
        msg = f"Project name does not produce a valid Python package name: {name}"
        raise ValueError(msg)
    return project_slug, package_name


def build_init_options(
    name: str,
    *,
    base_dir: Path,
    agent: AgentChoice,
    profile: ProfileChoice,
    license_name: LicenseChoice,
    python_min: str,
    coverage: int,
    ci: str,
    dry_run: bool,
    force: bool,
) -> InitOptions:
    """Build validated init options from CLI values."""
    stripped_name = name.strip()
    if stripped_name == ".":
        project_slug, package_name = normalize_project_name(base_dir.name)
        target_dir = base_dir
    else:
        project_slug, package_name = normalize_project_name(stripped_name)
        target_dir = base_dir / project_slug
    if profile not in SUPPORTED_PROFILES:
        msg = f"Unsupported project profile: {profile}"
        raise ValueError(msg)
    if ci != "github":
        msg = f"Unsupported CI provider: {ci}"
        raise ValueError(msg)
    return InitOptions(
        target_dir=target_dir,
        project_slug=project_slug,
        package_name=package_name,
        agent=agent,
        profile=profile,
        license=license_name,
        python_min=python_min,
        coverage=coverage,
        ci=ci,
        docs_enabled=profile == "package",
        dry_run=dry_run,
        force=force,
    )


def with_quality_tools(
    options: InitOptions,
    *,
    ruff: bool,
    mypy: bool,
    pyright: bool,
) -> InitOptions:
    """Return init options with explicit generated quality-tool selections."""
    return replace(options, ruff_enabled=ruff, mypy_enabled=mypy, pyright_enabled=pyright)


def build_render_context(options: InitOptions) -> Mapping[str, object]:
    """Return the shared template context for a generated package project."""
    ci_enabled = options.ci == "github"
    configured_tools = _format_tool_list(
        (
            *(() if not options.ruff_enabled else ("Ruff",)),
            *(() if not options.mypy_enabled else ("mypy",)),
            *(() if not options.pyright_enabled else ("Pyright",)),
            "pytest",
            "coverage",
            "MkDocs",
        )
    )
    return {
        "project_slug": options.project_slug,
        "package_name": options.package_name,
        "profile": options.profile,
        "license": options.license,
        "python_min": options.python_min,
        "coverage": options.coverage,
        "configured_tools": configured_tools,
        "use_ruff": options.ruff_enabled,
        "use_mypy": options.mypy_enabled,
        "use_pyright": options.pyright_enabled,
        "ruff_enabled": _toml_bool(options.ruff_enabled),
        "mypy_enabled": _toml_bool(options.mypy_enabled),
        "pyright_enabled": _toml_bool(options.pyright_enabled),
        "codex_enabled": _toml_bool(options.codex_enabled),
        "claude_enabled": _toml_bool(options.claude_enabled),
        "cursor_enabled": _toml_bool(options.cursor_enabled),
        "docs_enabled": _toml_bool(options.docs_enabled),
        "ci_enabled": _toml_bool(ci_enabled),
    }


def render_file(
    renderer: TemplateRenderer,
    *,
    template_name: str,
    destination: str,
    context: Mapping[str, object],
) -> RenderedFile:
    """Render one packaged template into a destination file model."""
    relative_destination = ensure_relative_safe_path(destination)
    return RenderedFile(
        path=relative_destination,
        content=renderer.render(template_name, context),
    )


def package_template_specs(options: InitOptions) -> tuple[TemplateSpec, ...]:
    """Return profile templates plus selected adapter templates."""
    adapter_specs = tuple(
        spec for adapter in adapters_for(options.agent) for spec in adapter.template_specs()
    )
    profile_specs: tuple[TemplateSpec, ...] = (
        MINIMAL_TEMPLATE_SPECS if options.profile == "minimal" else PACKAGE_TEMPLATE_SPECS
    )
    if options.profile == "package" and options.pyright_enabled:
        profile_specs = (
            *profile_specs,
            TemplateSpec("package/pyrightconfig.json.j2", "pyrightconfig.json"),
        )
    return (*profile_specs, *adapter_specs)


def render_package_files(
    options: InitOptions,
    *,
    renderer: TemplateRenderer | None = None,
) -> tuple[RenderedFile, ...]:
    """Render all files for a generated project profile."""
    active_renderer = renderer or TemplateRenderer()
    context = build_render_context(options)
    return tuple(
        render_file(
            active_renderer,
            template_name=spec.template_name,
            destination=spec.destination.format(package_name=options.package_name),
            context=context,
        )
        for spec in package_template_specs(options)
    )


def scaffold_package_project(
    options: InitOptions,
    *,
    renderer: TemplateRenderer | None = None,
) -> ScaffoldSummary:
    """Render and write, or dry-run, a generated project."""
    if options.target_dir.exists():
        if not options.target_dir.is_dir():
            msg = f"Target path is not a directory: {options.target_dir}"
            raise NotADirectoryError(msg)
        if any(options.target_dir.iterdir()) and not options.force:
            msg = (
                "Target directory already exists and is not empty; use --force to overwrite "
                "generated files: "
                f"{options.target_dir}"
            )
            raise FileExistsError(msg)

    rendered_files = render_package_files(options, renderer=renderer)
    planned_files = write_rendered_files(
        options.target_dir,
        rendered_files,
        dry_run=options.dry_run,
        force=options.force,
    )
    return ScaffoldSummary(
        target_dir=options.target_dir,
        files=planned_files,
        dry_run=options.dry_run,
    )


def write_rendered_files(
    target_dir: Path,
    files: Iterable[RenderedFile],
    *,
    dry_run: bool,
    force: bool,
) -> tuple[Path, ...]:
    """Validate and optionally write rendered files below `target_dir`."""
    file_list = tuple(files)
    base = target_dir.resolve(strict=False)
    planned_paths: list[Path] = []

    if target_dir.exists() and not target_dir.is_dir():
        msg = f"Target path is not a directory: {target_dir}"
        raise NotADirectoryError(msg)

    for rendered_file in file_list:
        relative_path = ensure_relative_safe_path(rendered_file.path.as_posix())
        output_path = base / relative_path
        if not is_within_directory(base, output_path):
            msg = f"Refusing to write outside target directory: {rendered_file.path}"
            raise ValueError(msg)
        planned_paths.append(relative_path)

    if dry_run:
        return tuple(planned_paths)

    base.mkdir(parents=True, exist_ok=True)
    for rendered_file, relative_path in zip(file_list, planned_paths, strict=True):
        output_path = base / relative_path
        write_text_safely(output_path, rendered_file.content, force=force)

    return tuple(planned_paths)


def _toml_bool(value: bool) -> str:
    """Render a Python boolean as TOML lowercase text."""
    return "true" if value else "false"


def _format_tool_list(tools: tuple[str, ...]) -> str:
    """Format configured tool names for generated prose."""
    pair_count = 2
    if len(tools) == 1:
        return tools[0]
    if len(tools) == pair_count:
        return f"{tools[0]} and {tools[1]}"
    return f"{', '.join(tools[:-1])}, and {tools[-1]}"
