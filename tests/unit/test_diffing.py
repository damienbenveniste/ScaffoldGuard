"""Unit tests for diff classification."""

from pathlib import Path

import pytest

from scaffold_guard.diffing import (
    DiffInspectionError,
    ProjectValidationSettings,
    classify_changed_files,
    inspect_diff,
    load_project_validation_settings,
)
from scaffold_guard.models import ProfileChoice, PythonQualityMode, PythonTypechecker
from scaffold_guard.scaffold import build_init_options, scaffold_package_project, with_quality_tools


def test_source_change_requires_tests_validation_and_docs_evidence(tmp_path: Path) -> None:
    """Source changes require the Python validation stack and test evidence."""
    root = _generated_project(tmp_path)
    changed_file = Path("src/demo/core.py")

    report = classify_changed_files(
        root,
        changed_files=(changed_file,),
        base="main",
        settings=ProjectValidationSettings(package_name="demo", coverage=95),
    )

    assert "uv run ruff format --check ." in report.required_validation
    assert "uv run mypy src tests" in report.required_validation
    assert "uv run pyright" in report.required_validation
    assert "uv run pytest tests --cov=demo --cov-fail-under=95" in report.required_validation
    assert "Python tests changed or added for behavior change" in report.required_evidence
    assert "docs or README updated because public source changed" in report.required_evidence
    assert any(area.label == "public API" for area in report.changed_areas)
    assert "Python source changed without a detected Python tests/ change." in report.warnings


def test_source_change_respects_disabled_quality_tools(tmp_path: Path) -> None:
    """Source validation hints omit disabled quality tools."""
    root = _generated_project(tmp_path)

    report = classify_changed_files(
        root,
        changed_files=(Path("src/demo/core.py"),),
        base="main",
        settings=ProjectValidationSettings(
            package_name="demo",
            coverage=95,
            ruff=False,
            mypy=False,
            pyright=False,
        ),
    )

    assert "uv run ruff format --check ." not in report.required_validation
    assert "uv run ruff check ." not in report.required_validation
    assert "uv run mypy src tests" not in report.required_validation
    assert "uv run pyright" not in report.required_validation
    assert "uv run pytest tests --cov=demo --cov-fail-under=95" in report.required_validation


def test_typescript_source_change_requires_npm_validation(tmp_path: Path) -> None:
    """TypeScript source changes require npm script validation and test evidence."""
    root = _generated_project(tmp_path, profile="typescript")
    changed_file = Path("src/index.ts")

    report = classify_changed_files(
        root,
        changed_files=(changed_file,),
        base="main",
        settings=ProjectValidationSettings(
            package_name="demo",
            coverage=95,
            profile="typescript",
            biome=True,
            vitest=True,
        ),
    )

    assert "npm run format:check" in report.required_validation
    assert "npm run lint" in report.required_validation
    assert "npm run typecheck" in report.required_validation
    assert "npm test" in report.required_validation
    assert "TypeScript tests changed or added for behavior change" in report.required_evidence
    assert any(area.label == "TypeScript source" for area in report.changed_areas)
    assert (
        "TypeScript source changed without a detected TypeScript tests/ change." in report.warnings
    )


def test_typescript_source_change_respects_disabled_optional_tools(tmp_path: Path) -> None:
    """TypeScript source validation hints omit disabled Biome and Vitest commands."""
    root = _generated_project(tmp_path, profile="typescript")

    report = classify_changed_files(
        root,
        changed_files=(Path("src/index.ts"),),
        base="main",
        settings=ProjectValidationSettings(
            package_name="demo",
            coverage=95,
            profile="typescript",
            biome=False,
            vitest=False,
        ),
    )

    assert report.required_validation == ("npm run typecheck",)
    assert "TypeScript tests changed or added for behavior change" not in report.required_evidence
    assert (
        "TypeScript source changed without a detected TypeScript tests/ change."
        not in report.warnings
    )


@pytest.mark.parametrize(
    ("python_workspace", "typescript_workspace"),
    [
        ("apps/api", "apps/web"),
        ("packages/core", "packages/client"),
        ("services/platform/backend", "clients/web/sdk"),
        ("packages/python", "packages/typescript"),
    ],
)
def test_monorepo_source_changes_require_language_scoped_validation(
    tmp_path: Path,
    python_workspace: str,
    typescript_workspace: str,
) -> None:
    """Mixed monorepo diffs produce scoped Python and TypeScript validation hints."""
    root = _generated_project(tmp_path, profile="monorepo")
    python_path = Path(python_workspace)
    typescript_path = Path(typescript_workspace)

    report = classify_changed_files(
        root,
        changed_files=(
            python_path / "src/demo/core.py",
            typescript_path / "src/index.ts",
            typescript_path / "tests/index.test.ts",
        ),
        base="main",
        settings=ProjectValidationSettings(
            package_name="demo",
            coverage=95,
            profile="monorepo",
            biome=True,
            vitest=True,
            python_workspace=python_path,
            typescript_workspace=typescript_path,
        ),
    )

    assert f"uv run ruff format --check {python_workspace}" in report.required_validation
    assert (
        f"uv run mypy {python_workspace}/src {python_workspace}/tests "
        f"{python_workspace}/examples" in report.required_validation
    )
    assert (
        f"uv run pytest {python_workspace}/tests --cov=demo --cov-fail-under=95"
        in report.required_validation
    )
    assert "npm run ts:format:check" in report.required_validation
    assert "npm run ts:typecheck" in report.required_validation
    assert "npm run ts:test" in report.required_validation
    assert "Python source changed without a detected Python tests/ change." in report.warnings
    assert "TypeScript source changed without a detected TypeScript tests/ change." not in (
        report.warnings
    )


def test_init_file_change_requires_import_integration_test(tmp_path: Path) -> None:
    """Package `__init__` changes require import integration validation."""
    root = _generated_project(tmp_path)

    report = classify_changed_files(
        root,
        changed_files=(Path("src/demo/__init__.py"), Path("tests/unit/test_core.py")),
        base="main",
        settings=ProjectValidationSettings(package_name="demo", coverage=95),
    )

    assert "uv run pytest tests/integration" in report.required_validation
    assert "import integration test run for package __init__ change" in report.required_evidence
    assert "Source changed without a detected tests/ change." not in report.warnings


def test_docs_only_change_requires_docs_validation(tmp_path: Path) -> None:
    """Docs-only changes require docs validation but not Python test validation."""
    root = _generated_project(tmp_path)

    report = classify_changed_files(
        root,
        changed_files=(Path("README.md"),),
        base="main",
        settings=ProjectValidationSettings(package_name="demo", coverage=95),
    )

    assert report.required_validation == ("uv run mkdocs build --strict", "git diff --check")
    assert report.required_evidence == ("final response lists validation commands run",)


def test_pyproject_change_warns_when_lockfile_exists_but_is_not_changed(tmp_path: Path) -> None:
    """pyproject changes warn when an existing lockfile is absent from the diff."""
    root = _generated_project(tmp_path)
    (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")

    report = classify_changed_files(
        root,
        changed_files=(Path("pyproject.toml"),),
        base="main",
        settings=ProjectValidationSettings(package_name="demo", coverage=95),
    )

    assert "uv lock or uv sync" in report.required_validation
    assert "pyproject.toml changed while uv.lock exists but is not in the diff." in report.warnings


def test_package_json_change_warns_when_lockfile_exists_but_is_not_changed(tmp_path: Path) -> None:
    """package.json changes warn when an existing package lock is absent from the diff."""
    root = _generated_project(tmp_path, profile="typescript")
    (root / "package-lock.json").write_text("{}\n", encoding="utf-8")

    report = classify_changed_files(
        root,
        changed_files=(Path("package.json"),),
        base="main",
        settings=ProjectValidationSettings(
            package_name="demo",
            coverage=95,
            profile="typescript",
            biome=True,
            vitest=True,
        ),
    )

    assert "npm install" in report.required_validation
    assert (
        "package-lock.json updated or dependency lock status explained" in report.required_evidence
    )
    assert (
        "package.json changed while package-lock.json exists but is not in the diff."
        in report.warnings
    )


def test_agent_rule_change_requires_scaffold_guard_check(tmp_path: Path) -> None:
    """Agent instruction changes require policy validation."""
    root = _generated_project(tmp_path)

    report = classify_changed_files(
        root,
        changed_files=(Path(".cursor/rules/python.mdc"),),
        base="main",
        settings=ProjectValidationSettings(package_name="demo", coverage=95),
    )

    assert report.required_validation == ("scaffold-guard check",)
    assert (
        "agent rules regenerated or rule compilation was not required" in report.required_evidence
    )


def test_workflow_and_example_changes_require_specific_evidence(tmp_path: Path) -> None:
    """Workflow and example changes add their own validation requirements."""
    root = _generated_project(tmp_path)

    report = classify_changed_files(
        root,
        changed_files=(
            Path(".github/workflows/ci.yml"),
            Path(".gitlab-ci.yml"),
            Path("examples/hello.py"),
            Path("LICENSE"),
            Path(".gitignore"),
        ),
        base="main",
        settings=ProjectValidationSettings(package_name="demo", coverage=95),
    )

    assert "manual CI workflow review" in report.required_validation
    assert "uv run pytest tests/integration" in report.required_validation
    assert any(area.label == "license" for area in report.changed_areas)
    assert any(area.label == "git ignore rules" for area in report.changed_areas)


def test_no_changes_have_no_required_actions(tmp_path: Path) -> None:
    """Empty diffs produce an empty action report."""
    root = _generated_project(tmp_path)

    report = classify_changed_files(
        root,
        changed_files=(),
        base="main",
        settings=ProjectValidationSettings(package_name="demo", coverage=95),
    )

    assert not report.has_changes
    assert report.required_validation == ()
    assert report.required_evidence == ()
    assert report.to_json()["changed_files"] == []


def test_load_project_validation_settings_reads_generated_config(tmp_path: Path) -> None:
    """Generated `scaffold-guard.toml` feeds project-specific command hints."""
    root = _generated_project(tmp_path)

    settings = load_project_validation_settings(root)

    assert settings == ProjectValidationSettings(package_name="demo", coverage=95)


def test_load_project_validation_settings_preserves_legacy_monorepo_defaults(
    tmp_path: Path,
) -> None:
    """A missing monorepo table retains the historical workspace paths."""
    root = tmp_path / "legacy"
    root.mkdir()
    (root / "scaffold-guard.toml").write_text(
        '[project]\nprofile = "monorepo"\npackage = "demo"\ncoverage_fail_under = 95\n',
        encoding="utf-8",
    )

    settings = load_project_validation_settings(root)

    assert settings.python_workspace == Path("packages/python")
    assert settings.typescript_workspace == Path("packages/typescript")


@pytest.mark.parametrize(
    ("layout", "python_workspace", "typescript_workspace", "match"),
    [
        ("custom", "../outside", "clients/web", "must not contain '..'"),
        ("custom", "services/api;echo-owned", "clients/web", "only letters"),
        ("custom", "services/api", "services/api/web", "must not overlap"),
        ("application", "services/api", "clients/web", "requires workspaces"),
    ],
)
def test_inspect_diff_rejects_invalid_configured_monorepo_workspaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    layout: str,
    python_workspace: str,
    typescript_workspace: str,
    match: str,
) -> None:
    """Unsafe or inconsistent workspace config fails before command guidance."""
    root = tmp_path / "invalid-workspaces"
    root.mkdir()
    (root / "scaffold-guard.toml").write_text(
        (
            '[project]\nprofile = "monorepo"\npackage = "demo"\ncoverage_fail_under = 95\n'
            f'\n[monorepo]\nlayout = "{layout}"\n'
            f'python_workspace = "{python_workspace}"\n'
            f'typescript_workspace = "{typescript_workspace}"\n'
        ),
        encoding="utf-8",
    )

    def is_git_repository(_root: Path) -> bool:
        return True

    def changed_files(
        _root: Path,
        *,
        base: str,
    ) -> tuple[tuple[Path, ...], tuple[str, ...]]:
        return ((Path(python_workspace) / "src/demo/core.py",), (base,))

    monkeypatch.setattr("scaffold_guard.diffing._is_git_repository", is_git_repository)
    monkeypatch.setattr(
        "scaffold_guard.diffing.collect_changed_files",
        changed_files,
    )

    with pytest.raises(DiffInspectionError, match=match):
        inspect_diff(root, base="main")


def test_load_project_validation_settings_reads_mode_aware_python_tools(tmp_path: Path) -> None:
    """Mode-aware Python tool config feeds validation command hints."""
    root = _generated_project(
        tmp_path,
        ruff_mode="standard",
        mypy=False,
        pyright=True,
        python_typecheck_mode="standard",
        python_typechecker="pyright",
    )

    settings = load_project_validation_settings(root)

    assert settings == ProjectValidationSettings(
        package_name="demo",
        coverage=95,
        ruff=True,
        mypy=False,
        pyright=True,
    )


def test_load_project_validation_settings_reads_mode_aware_python_tool_disablement(
    tmp_path: Path,
) -> None:
    """Mode-aware off settings remove Python quality validation command hints."""
    root = _generated_project(tmp_path, ruff=False, mypy=False, pyright=False)

    settings = load_project_validation_settings(root)

    assert settings == ProjectValidationSettings(
        package_name="demo",
        coverage=95,
        ruff=False,
        mypy=False,
        pyright=False,
    )


def test_inspect_diff_rejects_missing_or_non_git_paths(tmp_path: Path) -> None:
    """Diff inspection fails clearly outside git repositories."""
    with pytest.raises(DiffInspectionError, match="does not exist"):
        inspect_diff(tmp_path / "missing", base="main")
    with pytest.raises(DiffInspectionError, match="not a git repository"):
        inspect_diff(tmp_path, base="main")


def _generated_project(
    tmp_path: Path,
    *,
    profile: ProfileChoice = "python",
    ruff: bool = True,
    mypy: bool = True,
    pyright: bool = True,
    ruff_mode: PythonQualityMode = "strict",
    python_typecheck_mode: PythonQualityMode = "strict",
    python_typechecker: PythonTypechecker = "mypy+pyright",
) -> Path:
    """Create a standard generated project for diff classification tests."""
    options = build_init_options(
        "demo",
        base_dir=tmp_path,
        agent="all",
        profile=profile,
        license_name="MIT",
        python_min="3.13",
        coverage=95,
        ci="github",
        dry_run=False,
        force=False,
    )
    options = with_quality_tools(
        options,
        ruff=ruff,
        mypy=mypy,
        pyright=pyright,
        ruff_mode=ruff_mode,
        python_typecheck_mode=python_typecheck_mode,
        python_typechecker=python_typechecker,
    )
    scaffold_package_project(options)
    return tmp_path / "demo"
