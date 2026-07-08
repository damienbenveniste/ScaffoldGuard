"""Diff inspection for generated scaffold-guard repositories."""

import asyncio
import re
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from scaffold_guard.checks.config import (
    bool_value,
    int_value,
    load_scaffold_guard_toml,
    str_value,
    table_value,
)
from scaffold_guard.models import normalize_profile_choice

PUBLIC_SYMBOL: re.Pattern[str] = re.compile(
    r"^(?:def|class)\s+([A-Za-z][A-Za-z0-9_]*)\b",
    flags=re.MULTILINE,
)
PUBLIC_TYPESCRIPT_SYMBOL: re.Pattern[str] = re.compile(
    r"^export\s+(?:async\s+)?(?:function|class|const|let|interface|type|enum)\s+"
    r"([A-Za-z][A-Za-z0-9_]*)\b",
    flags=re.MULTILINE,
)
GIT_NOT_FOUND: int = 127


class DiffInspectionError(ValueError):
    """Raised when diff inspection cannot run for the requested project."""


@dataclass(frozen=True, slots=True)
class GitResult:
    """Result from a git command used during diff inspection."""

    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class DiffArea:
    """A changed file grouped into a user-facing impact area."""

    label: str
    path: Path

    def to_json(self) -> dict[str, object]:
        """Return a JSON-serializable changed area."""
        return {
            "label": self.label,
            "path": self.path.as_posix(),
        }


@dataclass(frozen=True, slots=True)
class DiffReport:
    """Diff impact report with required validation and evidence."""

    path: Path
    base: str
    changed_files: tuple[Path, ...]
    changed_areas: tuple[DiffArea, ...]
    required_validation: tuple[str, ...]
    required_evidence: tuple[str, ...]
    warnings: tuple[str, ...]
    collection_methods: tuple[str, ...]

    @property
    def has_changes(self) -> bool:
        """Return whether the inspected diff contains changed files."""
        return bool(self.changed_files)

    def to_json(self) -> dict[str, object]:
        """Return a JSON-serializable diff report."""
        return {
            "path": str(self.path),
            "base": self.base,
            "changed_files": [path.as_posix() for path in self.changed_files],
            "changed_areas": [area.to_json() for area in self.changed_areas],
            "required_validation": list(self.required_validation),
            "required_evidence": list(self.required_evidence),
            "warnings": list(self.warnings),
            "collection_methods": list(self.collection_methods),
        }


@dataclass(frozen=True, slots=True)
class ProjectValidationSettings:
    """Project-specific validation settings used in diff recommendations."""

    package_name: str | None
    coverage: int | None
    profile: str = "python"
    ruff: bool = True
    mypy: bool = True
    pyright: bool = True
    biome: bool = False
    vitest: bool = False


def inspect_diff(path: Path, *, base: str) -> DiffReport:
    """Collect changed files and classify required validation."""
    root = path.resolve(strict=False)
    if not root.exists():
        msg = f"Project path does not exist: {path}"
        raise DiffInspectionError(msg)
    if not root.is_dir():
        msg = f"Project path is not a directory: {path}"
        raise DiffInspectionError(msg)
    if not _is_git_repository(root):
        msg = f"Project path is not a git repository: {path}"
        raise DiffInspectionError(msg)

    changed_files, methods = collect_changed_files(root, base=base)
    settings = load_project_validation_settings(root)
    return classify_changed_files(
        root,
        changed_files=changed_files,
        base=base,
        settings=settings,
        collection_methods=methods,
    )


def collect_changed_files(root: Path, *, base: str) -> tuple[tuple[Path, ...], tuple[str, ...]]:
    """Collect changed files from base, staged, and unstaged git diffs."""
    collected: dict[str, Path] = {}
    methods: list[str] = []

    base_methods: tuple[tuple[str, tuple[str, ...]], ...] = (
        (f"{base}...HEAD", ("diff", "--name-only", f"{base}...HEAD")),
        (base, ("diff", "--name-only", base)),
    )
    for method, command in base_methods:
        result = _run_git(root, command)
        if result.returncode == 0:
            _add_changed_files(collected, result.stdout)
            methods.append(method)
            break

    for method, command in (
        ("--cached", ("diff", "--name-only", "--cached")),
        ("working-tree", ("diff", "--name-only")),
    ):
        result = _run_git(root, command)
        if result.returncode == 0:
            before = len(collected)
            _add_changed_files(collected, result.stdout)
            if len(collected) != before or result.stdout.strip():
                methods.append(method)

    return tuple(collected[name] for name in sorted(collected)), tuple(methods)


def classify_changed_files(
    root: Path,
    *,
    changed_files: Iterable[Path],
    base: str,
    settings: ProjectValidationSettings,
    collection_methods: tuple[str, ...] = (),
) -> DiffReport:
    """Map changed files to required validation and evidence."""
    files = tuple(sorted(changed_files))
    areas: list[DiffArea] = []
    validations: list[str] = []
    evidence: list[str] = []
    warnings: list[str] = []

    python_tests_changed = any(_is_python_test_file(path) for path in files)
    typescript_tests_changed = any(_is_typescript_test_file(path) for path in files)
    docs_changed = any(_is_docs_file(path) for path in files)

    for path in files:
        areas.extend(_classify_path(root, path))

    _apply_source_rules(
        root,
        files,
        settings,
        python_tests_changed,
        typescript_tests_changed,
        docs_changed,
        validations,
        evidence,
        warnings,
    )
    _apply_import_surface_rules(files, validations, evidence)
    _apply_tests_rules(
        python_tests_changed=python_tests_changed,
        typescript_tests_changed=typescript_tests_changed,
        settings=settings,
        validations=validations,
    )
    _apply_docs_rules(docs_changed, validations)
    _apply_pyproject_rules(root, files, validations, evidence, warnings)
    _apply_package_json_rules(root, files, validations, evidence, warnings)
    _apply_workflow_rules(files, validations, evidence)
    _apply_agent_rules(files, validations, evidence)
    _apply_example_rules(files, validations, evidence)

    if files:
        evidence.append("final response lists validation commands run")

    return DiffReport(
        path=root,
        base=base,
        changed_files=files,
        changed_areas=tuple(areas),
        required_validation=tuple(_dedupe(validations)),
        required_evidence=tuple(_dedupe(evidence)),
        warnings=tuple(_dedupe(warnings)),
        collection_methods=collection_methods,
    )


def load_project_validation_settings(root: Path) -> ProjectValidationSettings:
    """Load project package and coverage settings for validation command hints."""
    config = load_scaffold_guard_toml(root)
    project = table_value(config, "project")
    tools = table_value(config, "tools")
    raw_profile = str_value(project, "profile") or "package"
    profile: str
    try:
        profile = normalize_profile_choice(raw_profile)
    except ValueError:
        profile = raw_profile
    tool_default = profile in {"python", "monorepo"}
    ruff_mode = str_value(tools, "ruff_mode")
    typecheck_mode = str_value(tools, "python_typecheck")
    typechecker = str_value(tools, "python_typechecker") or "mypy+pyright"
    ruff = (
        ruff_mode != "off"
        if ruff_mode in {"strict", "standard", "off"}
        else bool_value(
            tools,
            "ruff",
            default=tool_default,
        )
    )
    if typecheck_mode in {"strict", "standard", "off"}:
        mypy = typecheck_mode != "off" and typechecker in {"mypy+pyright", "mypy"}
        pyright = typecheck_mode != "off" and typechecker in {"mypy+pyright", "pyright"}
    else:
        mypy = bool_value(tools, "mypy", default=tool_default)
        pyright = bool_value(tools, "pyright", default=tool_default)
    return ProjectValidationSettings(
        package_name=str_value(project, "package"),
        coverage=int_value(project, "coverage_fail_under"),
        profile=profile,
        ruff=ruff,
        mypy=mypy,
        pyright=pyright,
        biome=bool_value(tools, "biome", default=profile in {"typescript", "monorepo"}),
        vitest=bool_value(tools, "vitest", default=profile in {"typescript", "monorepo"}),
    )


def _classify_path(root: Path, path: Path) -> tuple[DiffArea, ...]:
    """Return user-facing changed area labels for a changed file."""
    areas: list[DiffArea] = []
    if _is_python_source_file(path):
        areas.append(DiffArea("Python package source", path))
        if _is_python_import_surface_file(path):
            areas.append(DiffArea("package import surface", path))
        if _is_public_api_change(root, path):
            areas.append(DiffArea("public API", path))
        return tuple(areas)
    if _is_typescript_source_file(path):
        areas.append(DiffArea("TypeScript source", path))
        if _is_public_api_change(root, path):
            areas.append(DiffArea("public API", path))
        return tuple(areas)

    for label, predicate in (
        ("tests", _is_test_file),
        ("public docs", _is_docs_file),
        ("package configuration", _is_pyproject_file),
        ("package configuration", _is_package_json_file),
        ("CI workflow", _is_workflow_file),
        ("agent instructions", _is_agent_rule_file),
        ("examples", _is_example_file),
        ("license", _is_license_file),
        ("git ignore rules", _is_gitignore_file),
    ):
        if predicate(path):
            areas.append(DiffArea(label, path))
            break
    if not areas:
        areas.append(DiffArea("other", path))
    return tuple(areas)


def _is_git_repository(root: Path) -> bool:
    """Return whether `root` is inside a git repository."""
    result = _run_git(root, ("rev-parse", "--is-inside-work-tree"))
    return result.returncode == 0 and result.stdout.strip() == "true"


def _run_git(root: Path, command: tuple[str, ...]) -> GitResult:
    """Run a git command without shell expansion."""
    git_path = shutil.which("git")
    if git_path is None:
        return GitResult(returncode=GIT_NOT_FOUND, stdout="", stderr="git executable not found")
    return asyncio.run(_run_process(root, git_path, command))


async def _run_process(root: Path, executable: str, args: tuple[str, ...]) -> GitResult:
    """Run a process and capture decoded output."""
    process = await asyncio.create_subprocess_exec(
        executable,
        *args,
        cwd=root,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return GitResult(
        returncode=process.returncode or 0,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
    )


def _add_changed_files(collected: dict[str, Path], stdout: str) -> None:
    """Add newline-delimited git paths to a stable mapping."""
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped:
            collected.setdefault(stripped, Path(stripped))


def _is_source_file(path: Path) -> bool:
    """Return whether a path is generated package source."""
    return _is_python_source_file(path) or _is_typescript_source_file(path)


def _is_python_source_file(path: Path) -> bool:
    """Return whether a path is Python package source."""
    return path.match("src/**/*.py") or path.match("packages/python/src/**/*.py")


def _is_typescript_source_file(path: Path) -> bool:
    """Return whether a path is TypeScript package source."""
    return (
        _is_inside(path, ("src",)) or _is_inside(path, ("packages", "typescript", "src"))
    ) and path.suffix in {".ts", ".tsx"}


def _is_test_file(path: Path) -> bool:
    """Return whether a path is a generated test file."""
    return _is_python_test_file(path) or _is_typescript_test_file(path)


def _is_python_test_file(path: Path) -> bool:
    """Return whether a path is a Python test file."""
    return path.match("tests/**/*.py") or path.match("packages/python/tests/**/*.py")


def _is_typescript_test_file(path: Path) -> bool:
    """Return whether a path is a TypeScript test file."""
    return (
        _is_inside(path, ("tests",)) or _is_inside(path, ("packages", "typescript", "tests"))
    ) and path.suffix in {".ts", ".tsx"}


def _is_docs_file(path: Path) -> bool:
    """Return whether a path is public documentation."""
    return path == Path("README.md") or (path.parts[0:1] == ("docs",) and path.suffix == ".md")


def _is_agent_rule_file(path: Path) -> bool:
    """Return whether a path is an agent instruction file."""
    return (
        path in {Path("AGENTS.md"), Path("CLAUDE.md")}
        or path.parts[0:1] == (".codex",)
        or path.parts[0:2] == (".cursor", "rules")
        or path.parts[0:2] == (".claude", "rules")
    )


def _is_pyproject_file(path: Path) -> bool:
    """Return whether a path is the Python project configuration."""
    return path == Path("pyproject.toml")


def _is_package_json_file(path: Path) -> bool:
    """Return whether a path is a Node package configuration."""
    return path == Path("package.json") or path.match("packages/typescript/package.json")


def _is_inside(path: Path, prefix: tuple[str, ...]) -> bool:
    """Return whether a relative path is inside the given path prefix."""
    return path.parts[: len(prefix)] == prefix and len(path.parts) > len(prefix)


def _is_workflow_file(path: Path) -> bool:
    """Return whether a path is a CI workflow file."""
    return (
        path.parts[0:2] == (".github", "workflows") and path.suffix in {".yaml", ".yml"}
    ) or path == Path(".gitlab-ci.yml")


def _is_example_file(path: Path) -> bool:
    """Return whether a path is a Python example file."""
    return (
        path.parts[0:1] == ("examples",) or path.parts[0:3] == ("packages", "python", "examples")
    ) and path.suffix == ".py"


def _is_license_file(path: Path) -> bool:
    """Return whether a path is the project license."""
    return path == Path("LICENSE")


def _is_gitignore_file(path: Path) -> bool:
    """Return whether a path is the project gitignore."""
    return path == Path(".gitignore")


def _is_public_api_change(root: Path, path: Path) -> bool:
    """Heuristically detect whether a changed source file touches public API."""
    if _is_python_import_surface_file(path):
        return True
    full_path = root / path
    if not full_path.exists():
        return False
    content = full_path.read_text(encoding="utf-8", errors="replace")
    if path.suffix in {".ts", ".tsx"}:
        return any(
            not match.group(1).startswith("_")
            for match in PUBLIC_TYPESCRIPT_SYMBOL.finditer(content)
        )
    return any(not match.group(1).startswith("_") for match in PUBLIC_SYMBOL.finditer(content))


def _is_python_import_surface_file(path: Path) -> bool:
    """Return whether a path is a Python package import surface."""
    return path.match("src/**/__init__.py") or path.match("packages/python/src/**/__init__.py")


def _apply_source_rules(
    root: Path,
    files: tuple[Path, ...],
    settings: ProjectValidationSettings,
    python_tests_changed: bool,
    typescript_tests_changed: bool,
    docs_changed: bool,
    validations: list[str],
    evidence: list[str],
    warnings: list[str],
) -> None:
    """Add requirements caused by source changes."""
    python_source_changed = any(_is_python_source_file(path) for path in files)
    typescript_source_changed = any(_is_typescript_source_file(path) for path in files)
    if python_source_changed:
        _apply_python_source_rules(
            settings,
            python_tests_changed,
            validations,
            evidence,
            warnings,
        )
    if typescript_source_changed:
        _apply_typescript_source_rules(
            settings,
            typescript_tests_changed,
            validations,
            evidence,
            warnings,
        )
    if (python_source_changed or typescript_source_changed) and any(
        _is_public_api_change(root, path) for path in files if _is_source_file(path)
    ):
        evidence.append("docs or README updated because public source changed")
        if not docs_changed:
            warnings.append("Public source changed without a detected docs or README change.")


def _apply_python_source_rules(
    settings: ProjectValidationSettings,
    tests_changed: bool,
    validations: list[str],
    evidence: list[str],
    warnings: list[str],
) -> None:
    """Add requirements caused by Python source changes."""
    if settings.ruff:
        _add_many(validations, _ruff_commands(settings))
    if settings.mypy:
        validations.append(_mypy_command(settings))
    if settings.pyright:
        validations.append("uv run pyright")
    validations.append(_pytest_command(settings))
    evidence.append("Python tests changed or added for behavior change")
    if not tests_changed:
        warnings.append("Python source changed without a detected Python tests/ change.")


def _apply_typescript_source_rules(
    settings: ProjectValidationSettings,
    tests_changed: bool,
    validations: list[str],
    evidence: list[str],
    warnings: list[str],
) -> None:
    """Add requirements caused by TypeScript source changes."""
    _add_many(validations, _typescript_commands(settings, include_build=False))
    if settings.vitest:
        evidence.append("TypeScript tests changed or added for behavior change")
    if settings.vitest and not tests_changed:
        warnings.append("TypeScript source changed without a detected TypeScript tests/ change.")


def _apply_import_surface_rules(
    files: tuple[Path, ...],
    validations: list[str],
    evidence: list[str],
) -> None:
    """Add requirements caused by package import surface changes."""
    if any(_is_python_import_surface_file(path) for path in files):
        validations.append(_python_integration_command(files))
        evidence.append("import integration test run for package __init__ change")


def _apply_tests_rules(
    *,
    python_tests_changed: bool,
    typescript_tests_changed: bool,
    settings: ProjectValidationSettings,
    validations: list[str],
) -> None:
    """Add requirements caused by test changes."""
    if python_tests_changed:
        validations.append(_python_test_command(settings))
    if typescript_tests_changed and settings.vitest:
        validations.append(_typescript_test_command(settings))


def _apply_docs_rules(docs_changed: bool, validations: list[str]) -> None:
    """Add requirements caused by docs changes."""
    if docs_changed:
        _add_many(validations, ("uv run mkdocs build --strict", "git diff --check"))


def _apply_pyproject_rules(
    root: Path,
    files: tuple[Path, ...],
    validations: list[str],
    evidence: list[str],
    warnings: list[str],
) -> None:
    """Add requirements caused by pyproject changes."""
    if not any(_is_pyproject_file(path) for path in files):
        return
    validations.append("uv lock or uv sync")
    evidence.append("lockfile updated or dependency lock status explained")
    if (root / "uv.lock").exists() and Path("uv.lock") not in files:
        warnings.append("pyproject.toml changed while uv.lock exists but is not in the diff.")


def _apply_package_json_rules(
    root: Path,
    files: tuple[Path, ...],
    validations: list[str],
    evidence: list[str],
    warnings: list[str],
) -> None:
    """Add requirements caused by Node package configuration changes."""
    if not any(_is_package_json_file(path) for path in files):
        return
    validations.append("npm install")
    evidence.append("package-lock.json updated or dependency lock status explained")
    if (root / "package-lock.json").exists() and Path("package-lock.json") not in files:
        warnings.append(
            "package.json changed while package-lock.json exists but is not in the diff."
        )


def _apply_workflow_rules(
    files: tuple[Path, ...],
    validations: list[str],
    evidence: list[str],
) -> None:
    """Add requirements caused by GitHub workflow changes."""
    if any(_is_workflow_file(path) for path in files):
        validations.append("manual CI workflow review")
        evidence.append("workflow changes manually reviewed")


def _apply_agent_rules(
    files: tuple[Path, ...],
    validations: list[str],
    evidence: list[str],
) -> None:
    """Add requirements caused by agent instruction changes."""
    if any(_is_agent_rule_file(path) for path in files):
        validations.append("scaffold-guard check")
        evidence.append("agent rules regenerated or rule compilation was not required")


def _apply_example_rules(
    files: tuple[Path, ...],
    validations: list[str],
    evidence: list[str],
) -> None:
    """Add requirements caused by example changes."""
    if any(_is_example_file(path) for path in files):
        validations.append(_python_integration_command(files))
        evidence.append("example smoke test or integration coverage run")


def _ruff_commands(settings: ProjectValidationSettings) -> tuple[str, str]:
    """Return Ruff validation commands for the generated project profile."""
    if settings.profile == "monorepo":
        return (
            "uv run ruff format --check packages/python",
            "uv run ruff check packages/python",
        )
    return ("uv run ruff format --check .", "uv run ruff check .")


def _mypy_command(settings: ProjectValidationSettings) -> str:
    """Return the mypy validation command for the generated project profile."""
    if settings.profile == "monorepo":
        return "uv run mypy packages/python/src packages/python/tests packages/python/examples"
    return "uv run mypy src tests"


def _pytest_command(settings: ProjectValidationSettings) -> str:
    """Return the most specific pytest validation command available."""
    test_path = "packages/python/tests" if settings.profile == "monorepo" else "tests"
    if settings.package_name and settings.coverage:
        return (
            f"uv run pytest {test_path} --cov={settings.package_name} "
            f"--cov-fail-under={settings.coverage}"
        )
    return f"uv run pytest {test_path}"


def _python_test_command(settings: ProjectValidationSettings) -> str:
    """Return the Python test command for the generated project profile."""
    if settings.profile == "monorepo":
        return "uv run pytest packages/python/tests"
    return "uv run pytest tests"


def _python_integration_command(files: tuple[Path, ...]) -> str:
    """Return an integration-test command for package or monorepo paths."""
    if any(path.parts[0:2] == ("packages", "python") for path in files):
        return "uv run pytest packages/python/tests/integration"
    return "uv run pytest tests/integration"


def _typescript_commands(
    settings: ProjectValidationSettings,
    *,
    include_build: bool,
) -> tuple[str, ...]:
    """Return TypeScript validation commands for the generated project profile."""
    prefix = "ts:" if settings.profile == "monorepo" else ""
    commands: list[str] = []
    if settings.biome:
        commands.extend((f"npm run {prefix}format:check", f"npm run {prefix}lint"))
    commands.append(f"npm run {prefix}typecheck")
    if settings.vitest:
        commands.append(_typescript_test_command(settings))
    if include_build:
        commands.append(f"npm run {prefix}build")
    return tuple(commands)


def _typescript_test_command(settings: ProjectValidationSettings) -> str:
    """Return the TypeScript test command for the generated project profile."""
    if settings.profile == "monorepo":
        return "npm run ts:test"
    return "npm test"


def _add_many(target: list[str], values: Iterable[str]) -> None:
    """Append multiple values to a list."""
    target.extend(values)


def _dedupe(values: Iterable[str]) -> list[str]:
    """Return values in first-seen order with duplicates removed."""
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped
