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
from scaffold_guard.scaffold import build_init_options, scaffold_package_project


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
    assert "tests changed or added for behavior change" in report.required_evidence
    assert "docs or README updated because public source changed" in report.required_evidence
    assert any(area.label == "public API" for area in report.changed_areas)
    assert "Source changed without a detected tests/ change." in report.warnings


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
            Path("examples/hello.py"),
            Path("LICENSE"),
            Path(".gitignore"),
        ),
        base="main",
        settings=ProjectValidationSettings(package_name="demo", coverage=95),
    )

    assert "manual GitHub Actions workflow review" in report.required_validation
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


def test_inspect_diff_rejects_missing_or_non_git_paths(tmp_path: Path) -> None:
    """Diff inspection fails clearly outside git repositories."""
    with pytest.raises(DiffInspectionError, match="does not exist"):
        inspect_diff(tmp_path / "missing", base="main")
    with pytest.raises(DiffInspectionError, match="not a git repository"):
        inspect_diff(tmp_path, base="main")


def _generated_project(tmp_path: Path) -> Path:
    """Create a standard generated project for diff classification tests."""
    options = build_init_options(
        "demo",
        base_dir=tmp_path,
        agent="all",
        profile="package",
        license_name="MIT",
        python_min="3.13",
        coverage=95,
        ci="github",
        dry_run=False,
        force=False,
    )
    scaffold_package_project(options)
    return tmp_path / "demo"
