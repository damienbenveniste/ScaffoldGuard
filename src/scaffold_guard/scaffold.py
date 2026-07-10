"""Scaffold planning and file writing helpers."""

import keyword
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from scaffold_guard import __version__
from scaffold_guard.adapters import adapters_for_selection
from scaffold_guard.fs import (
    ensure_relative_safe_path,
    has_symlink_component,
    is_within_directory,
    write_text_safely,
)
from scaffold_guard.manifest import (
    MANIFEST_RELATIVE_PATH,
    ManifestFile,
    ProjectManifest,
    content_sha256,
    manifest_json,
)
from scaffold_guard.models import (
    SUPPORTED_PROFILES,
    AgentChoice,
    CiChoice,
    InitOptions,
    LicenseChoice,
    ProfileChoice,
    PythonQualityMode,
    PythonTypechecker,
    ScaffoldSummary,
    TemplateLifecycle,
    TemplateSpec,
    normalize_profile_choice,
    profile_includes_python,
)
from scaffold_guard.renderer import TemplateRenderer
from scaffold_guard.versions import (
    GENERATED_PROJECT_MINIMUM_VERSION,
    MANIFEST_VERSION,
    PROJECT_FORMAT_VERSION,
)

PROJECT_NAME_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
PYTHON_MINOR_VERSION_PATTERN: re.Pattern[str] = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)$")
SUPPORTED_CI: tuple[CiChoice, ...] = ("github", "gitlab")


def _spec(
    template_name: str,
    destination: str,
    lifecycle: TemplateLifecycle | None = None,
) -> TemplateSpec:
    """Return a fully identified template spec."""
    return TemplateSpec(
        template_id=template_name.removesuffix(".j2"),
        template_name=template_name,
        destination=destination,
        lifecycle=lifecycle or _classify_lifecycle(destination),
    )


def _classify_lifecycle(destination: str) -> TemplateLifecycle:
    """Classify a generated destination for lifecycle tracking."""
    managed_destinations = {"AGENTS.md", "CLAUDE.md", ".gitlab-ci.yml"}
    managed_prefixes = (".codex/", ".claude/", ".cursor/", ".github/workflows/")
    if destination in managed_destinations or destination.startswith(managed_prefixes):
        return "managed"
    if destination in {
        "biome.json",
        "mkdocs.yml",
        "package.json",
        "pyproject.toml",
        "pyrightconfig.json",
        "scaffold-guard.toml",
        "tsconfig.build.json",
        "tsconfig.json",
        "vitest.config.ts",
        "packages/typescript/package.json",
        "packages/typescript/tsconfig.build.json",
        "packages/typescript/tsconfig.json",
        "packages/typescript/vitest.config.ts",
    }:
        return "structured"
    return "seed"


PACKAGE_BASE_TEMPLATE_SPECS: tuple[TemplateSpec, ...] = (
    _spec("package/AGENTS.md.j2", "AGENTS.md"),
    _spec("package/README.md.j2", "README.md"),
    _spec("package/LICENSE.j2", "LICENSE"),
    _spec("package/pyproject.toml.j2", "pyproject.toml"),
    _spec("package/mkdocs.yml.j2", "mkdocs.yml"),
    _spec("package/gitignore.j2", ".gitignore"),
    _spec("package/scaffold-guard.toml.j2", "scaffold-guard.toml"),
    _spec("package/docs/index.md.j2", "docs/index.md"),
    _spec("package/examples/hello.py.j2", "examples/hello.py"),
    _spec("package/src/package/__init__.py.j2", "src/{package_name}/__init__.py"),
    _spec("package/src/package/core.py.j2", "src/{package_name}/core.py"),
    _spec("package/src/package/py.typed.j2", "src/{package_name}/py.typed"),
    _spec("package/tests/unit/test_core.py.j2", "tests/unit/test_core.py"),
    _spec(
        "package/tests/integration/test_import_package.py.j2",
        "tests/integration/test_import_package.py",
    ),
)
PACKAGE_GITHUB_TEMPLATE_SPECS: tuple[TemplateSpec, ...] = (
    _spec("package/github/workflows/ci.yml.j2", ".github/workflows/ci.yml"),
    _spec("package/github/workflows/docs.yml.j2", ".github/workflows/docs.yml"),
)
PACKAGE_GITLAB_TEMPLATE_SPECS: tuple[TemplateSpec, ...] = (
    _spec("package/gitlab-ci.yml.j2", ".gitlab-ci.yml"),
)
MINIMAL_BASE_TEMPLATE_SPECS: tuple[TemplateSpec, ...] = (
    _spec("minimal/AGENTS.md.j2", "AGENTS.md"),
    _spec("minimal/README.md.j2", "README.md"),
    _spec("package/LICENSE.j2", "LICENSE"),
    _spec("minimal/pyproject.toml.j2", "pyproject.toml"),
    _spec("minimal/gitignore.j2", ".gitignore"),
    _spec("minimal/scaffold-guard.toml.j2", "scaffold-guard.toml"),
)
MINIMAL_GITHUB_TEMPLATE_SPECS: tuple[TemplateSpec, ...] = (
    _spec("minimal/github/workflows/ci.yml.j2", ".github/workflows/ci.yml"),
)
MINIMAL_GITLAB_TEMPLATE_SPECS: tuple[TemplateSpec, ...] = (
    _spec("minimal/gitlab-ci.yml.j2", ".gitlab-ci.yml"),
)
TYPESCRIPT_BASE_TEMPLATE_SPECS: tuple[TemplateSpec, ...] = (
    _spec("typescript/AGENTS.md.j2", "AGENTS.md"),
    _spec("typescript/README.md.j2", "README.md"),
    _spec("package/LICENSE.j2", "LICENSE"),
    _spec("typescript/pyproject.toml.j2", "pyproject.toml"),
    _spec("typescript/package.json.j2", "package.json"),
    _spec("typescript/tsconfig.json.j2", "tsconfig.json"),
    _spec("typescript/tsconfig.build.json.j2", "tsconfig.build.json"),
    _spec("typescript/biome.json.j2", "biome.json"),
    _spec("typescript/vitest.config.ts.j2", "vitest.config.ts"),
    _spec("typescript/gitignore.j2", ".gitignore"),
    _spec("typescript/scaffold-guard.toml.j2", "scaffold-guard.toml"),
    _spec("typescript/src/index.ts.j2", "src/index.ts"),
    _spec("typescript/tests/index.test.ts.j2", "tests/index.test.ts"),
)
TYPESCRIPT_GITHUB_TEMPLATE_SPECS: tuple[TemplateSpec, ...] = (
    _spec("typescript/github/workflows/ci.yml.j2", ".github/workflows/ci.yml"),
)
TYPESCRIPT_GITLAB_TEMPLATE_SPECS: tuple[TemplateSpec, ...] = (
    _spec("typescript/gitlab-ci.yml.j2", ".gitlab-ci.yml"),
)
MONOREPO_BASE_TEMPLATE_SPECS: tuple[TemplateSpec, ...] = (
    _spec("monorepo/AGENTS.md.j2", "AGENTS.md"),
    _spec("monorepo/README.md.j2", "README.md"),
    _spec("package/LICENSE.j2", "LICENSE"),
    _spec("monorepo/pyproject.toml.j2", "pyproject.toml"),
    _spec("monorepo/package.json.j2", "package.json"),
    _spec("monorepo/biome.json.j2", "biome.json"),
    _spec("monorepo/gitignore.j2", ".gitignore"),
    _spec("monorepo/scaffold-guard.toml.j2", "scaffold-guard.toml"),
    _spec("monorepo/packages/python/examples/hello.py.j2", "packages/python/examples/hello.py"),
    _spec(
        "monorepo/packages/python/src/package/__init__.py.j2",
        "packages/python/src/{package_name}/__init__.py",
    ),
    _spec(
        "monorepo/packages/python/src/package/core.py.j2",
        "packages/python/src/{package_name}/core.py",
    ),
    _spec(
        "monorepo/packages/python/src/package/py.typed.j2",
        "packages/python/src/{package_name}/py.typed",
    ),
    _spec(
        "monorepo/packages/python/tests/unit/test_core.py.j2",
        "packages/python/tests/unit/test_core.py",
    ),
    _spec(
        "monorepo/packages/python/tests/integration/test_import_package.py.j2",
        "packages/python/tests/integration/test_import_package.py",
    ),
    _spec("monorepo/packages/typescript/package.json.j2", "packages/typescript/package.json"),
    _spec("monorepo/packages/typescript/tsconfig.json.j2", "packages/typescript/tsconfig.json"),
    _spec(
        "monorepo/packages/typescript/tsconfig.build.json.j2",
        "packages/typescript/tsconfig.build.json",
    ),
    _spec(
        "monorepo/packages/typescript/vitest.config.ts.j2",
        "packages/typescript/vitest.config.ts",
    ),
    _spec("monorepo/packages/typescript/src/index.ts.j2", "packages/typescript/src/index.ts"),
    _spec(
        "monorepo/packages/typescript/tests/index.test.ts.j2",
        "packages/typescript/tests/index.test.ts",
    ),
)
MONOREPO_GITHUB_TEMPLATE_SPECS: tuple[TemplateSpec, ...] = (
    _spec("monorepo/github/workflows/ci.yml.j2", ".github/workflows/ci.yml"),
)
MONOREPO_GITLAB_TEMPLATE_SPECS: tuple[TemplateSpec, ...] = (
    _spec("monorepo/gitlab-ci.yml.j2", ".gitlab-ci.yml"),
)
CONFLICT_DISPLAY_LIMIT: int = 5


@dataclass(frozen=True, slots=True)
class RenderedFile:
    """A generated file path and its rendered text content."""

    path: Path
    content: str
    template_id: str = "manual/rendered-file"
    lifecycle: TemplateLifecycle = "managed"


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
    ci: CiChoice,
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
    canonical_profile = normalize_profile_choice(profile)
    if ci not in SUPPORTED_CI:
        msg = f"Unsupported CI provider: {ci}"
        raise ValueError(msg)
    return InitOptions(
        target_dir=target_dir,
        project_slug=project_slug,
        package_name=package_name,
        agent=agent,
        profile=canonical_profile,
        license=license_name,
        python_min=python_min,
        coverage=coverage,
        ci=ci,
        docs_enabled=canonical_profile == "python",
        dry_run=dry_run,
        force=force,
    )


def with_quality_tools(
    options: InitOptions,
    *,
    ruff: bool,
    mypy: bool,
    pyright: bool,
    ruff_mode: PythonQualityMode = "strict",
    python_typecheck_mode: PythonQualityMode = "strict",
    python_typechecker: PythonTypechecker = "mypy+pyright",
    typescript_strict: bool = True,
    biome: bool = True,
    vitest: bool = True,
) -> InitOptions:
    """Return init options with explicit generated quality-tool selections."""
    return replace(
        options,
        ruff_enabled=ruff,
        mypy_enabled=mypy,
        pyright_enabled=pyright,
        ruff_mode=ruff_mode if ruff else "off",
        python_typecheck_mode=python_typecheck_mode if (mypy or pyright) else "off",
        python_typechecker=python_typechecker,
        typescript_strict_enabled=typescript_strict,
        biome_enabled=biome,
        vitest_enabled=vitest,
    )


def build_render_context(options: InitOptions) -> Mapping[str, object]:
    """Return the shared template context for a generated package project."""
    github_actions_enabled = options.ci == "github"
    gitlab_ci_enabled = options.ci == "gitlab"
    ci_enabled = github_actions_enabled or gitlab_ci_enabled
    configured_tools = _format_tool_list(
        (
            *(() if not options.ruff_enabled else ("Ruff",)),
            *(() if not options.mypy_enabled else ("mypy",)),
            *(() if not options.pyright_enabled else ("Pyright",)),
            "pytest",
            "coverage",
            *(() if not options.docs_enabled else ("MkDocs",)),
        )
    )
    return {
        "project_slug": options.project_slug,
        "package_name": options.package_name,
        "typescript_package_name": options.project_slug,
        "profile": options.profile,
        "license": options.license,
        "python_min": options.python_min,
        "generated_project_minimum_version": GENERATED_PROJECT_MINIMUM_VERSION,
        "ruff_target_version": _ruff_target_version(options.python_min),
        "coverage": options.coverage,
        "ci_provider": options.ci,
        "configured_tools": configured_tools,
        "use_ruff": options.ruff_enabled,
        "use_mypy": options.mypy_enabled,
        "use_pyright": options.pyright_enabled,
        "ruff_mode": options.ruff_mode,
        "python_typecheck_mode": options.python_typecheck_mode,
        "python_typechecker": options.python_typechecker,
        "use_ruff_strict": options.ruff_mode == "strict",
        "use_python_typecheck_strict": options.python_typecheck_mode == "strict",
        "use_typescript_strict": options.typescript_strict_enabled,
        "use_biome": options.biome_enabled,
        "use_vitest": options.vitest_enabled,
        "use_python": options.python_enabled,
        "use_typescript": options.typescript_enabled,
        "ruff_enabled": _toml_bool(options.ruff_enabled),
        "mypy_enabled": _toml_bool(options.mypy_enabled),
        "pyright_enabled": _toml_bool(options.pyright_enabled),
        "typescript_strict_enabled": _toml_bool(options.typescript_strict_enabled),
        "biome_enabled": _toml_bool(options.biome_enabled),
        "vitest_enabled": _toml_bool(options.vitest_enabled),
        "python_enabled": _toml_bool(options.python_enabled),
        "typescript_enabled": _toml_bool(options.typescript_enabled),
        "codex_enabled": _toml_bool(options.codex_enabled),
        "claude_enabled": _toml_bool(options.claude_enabled),
        "cursor_enabled": _toml_bool(options.cursor_enabled),
        "docs_enabled": _toml_bool(options.docs_enabled),
        "ci_enabled": _toml_bool(ci_enabled),
        "github_actions_enabled": _toml_bool(github_actions_enabled),
        "gitlab_ci_enabled": _toml_bool(gitlab_ci_enabled),
        "scaffold_guard_version": __version__,
        "generated_project_minimum_specifier": f">={GENERATED_PROJECT_MINIMUM_VERSION}",
        "project_format_version": PROJECT_FORMAT_VERSION,
    }


def render_file(
    renderer: TemplateRenderer,
    *,
    template_name: str,
    destination: str,
    template_id: str,
    lifecycle: TemplateLifecycle,
    context: Mapping[str, object],
) -> RenderedFile:
    """Render one packaged template into a destination file model."""
    relative_destination = ensure_relative_safe_path(destination)
    return RenderedFile(
        path=relative_destination,
        content=renderer.render(template_name, context),
        template_id=template_id,
        lifecycle=lifecycle,
    )


def package_template_specs(options: InitOptions) -> tuple[TemplateSpec, ...]:
    """Return profile templates plus selected adapter templates."""
    adapter_specs = _adapter_template_specs(options)
    profile_specs = _filtered_profile_template_specs(options)
    if (
        profile_includes_python(options.profile)
        and options.profile != "monorepo"
        and options.pyright_enabled
    ):
        profile_specs = (
            *profile_specs,
            _spec("package/pyrightconfig.json.j2", "pyrightconfig.json"),
        )
    if options.profile == "monorepo" and options.pyright_enabled:
        profile_specs = (
            *profile_specs,
            _spec("monorepo/pyrightconfig.json.j2", "pyrightconfig.json"),
        )
    return (*profile_specs, *adapter_specs)


def _filtered_profile_template_specs(options: InitOptions) -> tuple[TemplateSpec, ...]:
    """Return profile templates after removing disabled optional tool files."""
    profile_specs = _profile_template_specs(options)
    skipped_destinations: set[str] = set()
    if options.typescript_enabled and not options.biome_enabled:
        skipped_destinations.add("biome.json")
    if options.profile == "typescript" and not options.vitest_enabled:
        skipped_destinations.update({"vitest.config.ts", "tests/index.test.ts"})
    if options.profile == "monorepo" and not options.vitest_enabled:
        skipped_destinations.update(
            {
                "packages/typescript/vitest.config.ts",
                "packages/typescript/tests/index.test.ts",
            }
        )
    return tuple(spec for spec in profile_specs if spec.destination not in skipped_destinations)


def _adapter_template_specs(options: InitOptions) -> tuple[TemplateSpec, ...]:
    """Return selected adapter templates filtered for generated languages."""
    base_specs = tuple(
        spec
        for adapter in adapters_for_selection(options.adapter_selection)
        for spec in adapter.template_specs()
    )
    filtered_specs = tuple(
        spec
        for spec in base_specs
        if options.python_enabled
        or spec.destination
        not in {
            ".claude/rules/python.md",
            ".cursor/rules/python.mdc",
        }
    )
    ts_specs: list[TemplateSpec] = []
    if options.typescript_enabled and "claude" in options.adapter_selection:
        ts_specs.append(
            _spec("agents/claude/rules/typescript.md.j2", ".claude/rules/typescript.md")
        )
    if options.typescript_enabled and "cursor" in options.adapter_selection:
        ts_specs.append(
            _spec("agents/cursor/rules/typescript.mdc.j2", ".cursor/rules/typescript.mdc")
        )
    return (*filtered_specs, *ts_specs)


def _profile_template_specs(options: InitOptions) -> tuple[TemplateSpec, ...]:
    """Return base profile templates plus selected CI provider templates."""
    base_specs, github_specs, gitlab_specs = _profile_spec_groups(options.profile)
    ci_specs = gitlab_specs if options.ci == "gitlab" else github_specs
    return (*base_specs, *ci_specs)


def _profile_spec_groups(
    profile: ProfileChoice,
) -> tuple[tuple[TemplateSpec, ...], tuple[TemplateSpec, ...], tuple[TemplateSpec, ...]]:
    """Return base, GitHub, and GitLab template groups for a profile."""
    if profile == "minimal":
        return (
            MINIMAL_BASE_TEMPLATE_SPECS,
            MINIMAL_GITHUB_TEMPLATE_SPECS,
            MINIMAL_GITLAB_TEMPLATE_SPECS,
        )
    if profile == "typescript":
        return (
            TYPESCRIPT_BASE_TEMPLATE_SPECS,
            TYPESCRIPT_GITHUB_TEMPLATE_SPECS,
            TYPESCRIPT_GITLAB_TEMPLATE_SPECS,
        )
    if profile == "monorepo":
        return (
            MONOREPO_BASE_TEMPLATE_SPECS,
            MONOREPO_GITHUB_TEMPLATE_SPECS,
            MONOREPO_GITLAB_TEMPLATE_SPECS,
        )
    return PACKAGE_BASE_TEMPLATE_SPECS, PACKAGE_GITHUB_TEMPLATE_SPECS, PACKAGE_GITLAB_TEMPLATE_SPECS


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
            template_id=spec.template_id,
            lifecycle=spec.lifecycle,
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
    if options.target_dir.exists() and not options.target_dir.is_dir():
        msg = f"Target path is not a directory: {options.target_dir}"
        raise NotADirectoryError(msg)

    rendered_files = render_package_files(options, renderer=renderer)
    manifest = build_project_manifest(options, rendered_files)
    manifest_file = RenderedFile(
        path=Path(MANIFEST_RELATIVE_PATH),
        content=manifest_json(manifest),
        template_id="scaffold-guard/manifest",
        lifecycle="managed",
    )
    planned_files = write_rendered_files(
        options.target_dir,
        (*rendered_files, manifest_file),
        dry_run=options.dry_run,
        force=options.force,
    )
    return ScaffoldSummary(
        target_dir=options.target_dir,
        files=planned_files,
        dry_run=options.dry_run,
    )


def build_project_manifest(
    options: InitOptions,
    rendered_files: Iterable[RenderedFile],
) -> ProjectManifest:
    """Build lifecycle metadata for a rendered generated project."""
    manifest_files = tuple(
        ManifestFile(
            path=file.path.as_posix(),
            template_id=file.template_id,
            sha256=content_sha256(file.content),
        )
        for file in sorted(rendered_files, key=lambda rendered_file: rendered_file.path.as_posix())
        if file.lifecycle == "managed"
    )
    return ProjectManifest(
        manifest_version=MANIFEST_VERSION,
        project_format_version=PROJECT_FORMAT_VERSION,
        generated_with=__version__,
        requires_scaffold_guard=f">={GENERATED_PROJECT_MINIMUM_VERSION}",
        profile=normalize_profile_choice(options.profile),
        adapters=options.adapter_selection,
        files=manifest_files,
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
        if has_symlink_component(base, relative_path):
            msg = f"Refusing to write through symbolic link: {rendered_file.path}"
            raise FileExistsError(msg)
        if not is_within_directory(base, output_path):
            msg = f"Refusing to write outside target directory: {rendered_file.path}"
            raise ValueError(msg)
        planned_paths.append(relative_path)

    if dry_run:
        return tuple(planned_paths)

    if not force:
        existing_destinations = tuple(
            path for path in planned_paths if (base / path).exists() or (base / path).is_symlink()
        )
        if existing_destinations:
            formatted_paths = ", ".join(
                path.as_posix() for path in existing_destinations[:CONFLICT_DISPLAY_LIMIT]
            )
            if len(existing_destinations) > CONFLICT_DISPLAY_LIMIT:
                formatted_paths = f"{formatted_paths}, ..."
            msg = (
                "Target already contains file(s) ScaffoldGuard would generate; use --force "
                "to overwrite generated files: "
                f"{formatted_paths}"
            )
            raise FileExistsError(msg)

    base.mkdir(parents=True, exist_ok=True)
    for rendered_file, relative_path in zip(file_list, planned_paths, strict=True):
        output_path = base / relative_path
        write_text_safely(output_path, rendered_file.content, force=force)

    return tuple(planned_paths)


def _toml_bool(value: bool) -> str:
    """Render a Python boolean as TOML lowercase text."""
    return "true" if value else "false"


def _ruff_target_version(python_min: str) -> str:
    """Return Ruff's compact target-version value for a major.minor Python version."""
    match = PYTHON_MINOR_VERSION_PATTERN.fullmatch(python_min)
    if match is None:
        msg = f"Python minimum version must use major.minor format: {python_min}"
        raise ValueError(msg)
    return f"py{match['major']}{match['minor']}"


def _format_tool_list(tools: tuple[str, ...]) -> str:
    """Format configured tool names for generated prose."""
    pair_count = 2
    if len(tools) == 1:
        return tools[0]
    if len(tools) == pair_count:
        return f"{tools[0]} and {tools[1]}"
    return f"{', '.join(tools[:-1])}, and {tools[-1]}"
