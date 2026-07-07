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

PUBLIC_SYMBOL = re.compile(r"^(?:def|class)\s+([A-Za-z][A-Za-z0-9_]*)\b", flags=re.MULTILINE)
GIT_NOT_FOUND = 127


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
    ruff: bool = True
    mypy: bool = True
    pyright: bool = True


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

    tests_changed = any(_is_test_file(path) for path in files)
    docs_changed = any(_is_docs_file(path) for path in files)

    for path in files:
        areas.extend(_classify_path(root, path))

    _apply_source_rules(
        root,
        files,
        settings,
        tests_changed,
        docs_changed,
        validations,
        evidence,
        warnings,
    )
    _apply_import_surface_rules(files, validations, evidence)
    _apply_tests_rules(tests_changed, validations)
    _apply_docs_rules(docs_changed, validations)
    _apply_pyproject_rules(root, files, validations, evidence, warnings)
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
    tool_default = (str_value(project, "profile") or "package") == "package"
    return ProjectValidationSettings(
        package_name=str_value(project, "package"),
        coverage=int_value(project, "coverage_fail_under"),
        ruff=bool_value(tools, "ruff", default=tool_default),
        mypy=bool_value(tools, "mypy", default=tool_default),
        pyright=bool_value(tools, "pyright", default=tool_default),
    )


def _classify_path(root: Path, path: Path) -> tuple[DiffArea, ...]:
    """Return user-facing changed area labels for a changed file."""
    areas: list[DiffArea] = []
    if _is_source_file(path):
        areas.append(DiffArea("package source", path))
        if path.match("src/**/__init__.py"):
            areas.append(DiffArea("package import surface", path))
        if _is_public_api_change(root, path):
            areas.append(DiffArea("public API", path))
        return tuple(areas)

    for label, predicate in (
        ("tests", _is_test_file),
        ("public docs", _is_docs_file),
        ("package configuration", _is_pyproject_file),
        ("GitHub Actions workflow", _is_workflow_file),
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
    """Return whether a path is Python package source."""
    return path.match("src/**/*.py")


def _is_test_file(path: Path) -> bool:
    """Return whether a path is a Python test file."""
    return path.match("tests/**/*.py")


def _is_docs_file(path: Path) -> bool:
    """Return whether a path is public documentation."""
    return path == Path("README.md") or (path.parts[0:1] == ("docs",) and path.suffix == ".md")


def _is_agent_rule_file(path: Path) -> bool:
    """Return whether a path is an agent instruction file."""
    return (
        path in {Path("AGENTS.md"), Path("CLAUDE.md")}
        or path.parts[0:2] == (".cursor", "rules")
        or path.parts[0:2] == (".claude", "rules")
    )


def _is_pyproject_file(path: Path) -> bool:
    """Return whether a path is the Python project configuration."""
    return path == Path("pyproject.toml")


def _is_workflow_file(path: Path) -> bool:
    """Return whether a path is a GitHub Actions workflow file."""
    return path.parts[0:2] == (".github", "workflows") and path.suffix in {".yaml", ".yml"}


def _is_example_file(path: Path) -> bool:
    """Return whether a path is a Python example file."""
    return path.parts[0:1] == ("examples",) and path.suffix == ".py"


def _is_license_file(path: Path) -> bool:
    """Return whether a path is the project license."""
    return path == Path("LICENSE")


def _is_gitignore_file(path: Path) -> bool:
    """Return whether a path is the project gitignore."""
    return path == Path(".gitignore")


def _is_public_api_change(root: Path, path: Path) -> bool:
    """Heuristically detect whether a changed source file touches public API."""
    if path.match("src/**/__init__.py"):
        return True
    full_path = root / path
    if not full_path.exists():
        return False
    content = full_path.read_text(encoding="utf-8", errors="replace")
    return any(not match.group(1).startswith("_") for match in PUBLIC_SYMBOL.finditer(content))


def _apply_source_rules(
    root: Path,
    files: tuple[Path, ...],
    settings: ProjectValidationSettings,
    tests_changed: bool,
    docs_changed: bool,
    validations: list[str],
    evidence: list[str],
    warnings: list[str],
) -> None:
    """Add requirements caused by source changes."""
    if not any(_is_source_file(path) for path in files):
        return
    if settings.ruff:
        _add_many(
            validations,
            ("uv run ruff format --check .", "uv run ruff check ."),
        )
    if settings.mypy:
        validations.append("uv run mypy src tests")
    if settings.pyright:
        validations.append("uv run pyright")
    validations.append(_pytest_command(settings))
    evidence.append("tests changed or added for behavior change")
    if not tests_changed:
        warnings.append("Source changed without a detected tests/ change.")
    if any(_is_public_api_change(root, path) for path in files if _is_source_file(path)):
        evidence.append("docs or README updated because public source changed")
        if not docs_changed:
            warnings.append("Public source changed without a detected docs or README change.")


def _apply_import_surface_rules(
    files: tuple[Path, ...],
    validations: list[str],
    evidence: list[str],
) -> None:
    """Add requirements caused by package import surface changes."""
    if any(path.match("src/**/__init__.py") for path in files):
        validations.append("uv run pytest tests/integration")
        evidence.append("import integration test run for package __init__ change")


def _apply_tests_rules(tests_changed: bool, validations: list[str]) -> None:
    """Add requirements caused by test changes."""
    if tests_changed:
        validations.append("uv run pytest tests")


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


def _apply_workflow_rules(
    files: tuple[Path, ...],
    validations: list[str],
    evidence: list[str],
) -> None:
    """Add requirements caused by GitHub workflow changes."""
    if any(_is_workflow_file(path) for path in files):
        validations.append("manual GitHub Actions workflow review")
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
        validations.append("uv run pytest tests/integration")
        evidence.append("example smoke test or integration coverage run")


def _pytest_command(settings: ProjectValidationSettings) -> str:
    """Return the most specific pytest validation command available."""
    if settings.package_name and settings.coverage:
        return (
            f"uv run pytest tests --cov={settings.package_name} "
            f"--cov-fail-under={settings.coverage}"
        )
    return "uv run pytest tests"


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
