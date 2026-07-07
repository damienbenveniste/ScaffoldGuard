"""Unit tests for generated-project checkers."""

import os
from pathlib import Path

import pytest

from scaffold_guard.adapters.base import adapters_for
from scaffold_guard.checks.base import CheckConfigurationError, CheckResult, finding
from scaffold_guard.checks.config import ci_enabled, docs_enabled, table_value
from scaffold_guard.checks.config_consistency import check_config_consistency
from scaffold_guard.checks.files import gitignore_entries, iter_text_files
from scaffold_guard.checks.generated_files import check_generated_files
from scaffold_guard.checks.project_health import check_project_health
from scaffold_guard.checks.runner import run_checks
from scaffold_guard.checks.unsafe_patterns import check_unsafe_patterns
from scaffold_guard.scaffold import build_init_options, scaffold_package_project


def test_check_result_ok_ignores_warnings() -> None:
    """Warnings should not fail a checker."""
    result = CheckResult(
        id="demo",
        findings=(
            finding(
                "uv.lock",
                line=0,
                severity="warning",
                code="lockfile-warning",
                message="warning",
            ),
        ),
    )

    assert result.ok
    assert result.to_json()["ok"] is True


def test_adapters_for_single_adapter_selections() -> None:
    """Adapter selection returns the requested concrete adapter only."""
    assert adapters_for("claude")[0].__class__.__name__ == "ClaudeAdapter"
    assert adapters_for("cursor")[0].__class__.__name__ == "CursorAdapter"


def test_run_checks_fails_missing_project_path(tmp_path: Path) -> None:
    """Invalid check targets raise a configuration error."""
    missing = tmp_path / "missing"

    with pytest.raises(CheckConfigurationError, match="does not exist"):
        run_checks(missing)


def test_run_checks_fails_file_path(tmp_path: Path) -> None:
    """A file cannot be checked as a project root."""
    file_path = tmp_path / "file.txt"
    file_path.write_text("content\n", encoding="utf-8")

    with pytest.raises(CheckConfigurationError, match="not a directory"):
        run_checks(file_path)


def test_config_helpers_default_when_config_missing(tmp_path: Path) -> None:
    """Missing optional generated config falls back to enabled features."""
    assert docs_enabled(tmp_path)
    assert ci_enabled(tmp_path)
    assert table_value({"project": "not-table"}, "project") == {}


def test_file_helpers_ignore_runtime_cache_dirs_and_comments(tmp_path: Path) -> None:
    """Text discovery skips ignored runtime directories and gitignore comments."""
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv/ignored.py").write_text("bad\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    expected = tmp_path / "src/demo.py"
    expected.write_text("ok\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("# comment\n.venv/\n\n", encoding="utf-8")

    assert list(iter_text_files(tmp_path, [Path("src"), Path(".venv")])) == [expected]
    assert gitignore_entries(tmp_path) == {".venv"}


def test_unsafe_patterns_detects_type_ignore(tmp_path: Path) -> None:
    """The unsafe-pattern checker detects hidden typing suppressions."""
    project_dir = _generated_project(tmp_path)
    core_path = project_dir / "src/demo/core.py"
    core_path.write_text(core_path.read_text(encoding="utf-8") + "\nvalue = 1  # type: ignore\n")

    result = check_unsafe_patterns(project_dir)

    assert not result.ok
    assert any(finding.code == "no-type-ignore" for finding in result.findings)


def test_unsafe_patterns_respects_disabled_suppression_policies(tmp_path: Path) -> None:
    """Tool-specific suppression bans follow generated policy config."""
    project_dir = _generated_project(tmp_path)
    core_path = project_dir / "src/demo/core.py"
    core_path.write_text(
        "\n".join(
            [
                core_path.read_text(encoding="utf-8"),
                "value = 1  # type: ignore",
                "other = 2  # pyright: ignore",
                "lint = 3  # noqa: F841",
            ]
        ),
        encoding="utf-8",
    )
    _replace_text(
        project_dir / "scaffold-guard.toml",
        "forbid_type_ignore = true",
        "forbid_type_ignore = false",
    )
    _replace_text(
        project_dir / "scaffold-guard.toml",
        "forbid_pyright_ignore = true",
        "forbid_pyright_ignore = false",
    )
    _replace_text(project_dir / "scaffold-guard.toml", "forbid_noqa = true", "forbid_noqa = false")

    result = check_unsafe_patterns(project_dir)
    codes = {finding.code for finding in result.findings}

    assert "no-type-ignore" not in codes
    assert "no-pyright-ignore" not in codes
    assert "no-noqa" not in codes


def test_unsafe_patterns_detects_additional_risky_code(tmp_path: Path) -> None:
    """Unsafe-patterns catches typing, secret, shell, and absolute-write issues."""
    project_dir = _generated_project(tmp_path)
    risky_path = project_dir / "src/demo/risky.py"
    risky_path.write_text(
        "\n".join(
            [
                "from typing import Any",
                "import subprocess",
                "from pathlib import Path",
                'password = "secret"',
                "value: dict[str, Any] = {}",
                "subprocess.run('echo bad', shell=True)",
                "Path('/tmp/out.txt').write_text('bad')",
            ]
        ),
        encoding="utf-8",
    )

    result = check_unsafe_patterns(project_dir)
    codes = {finding.code for finding in result.findings}

    assert {
        "no-any-import",
        "secret-password-literal",
        "no-dict-str-any",
        "no-shell-true",
        "no-absolute-write",
    }.issubset(codes)


def test_unsafe_patterns_detects_env_file(tmp_path: Path) -> None:
    """Secret-bearing local environment files are policy failures."""
    project_dir = _generated_project(tmp_path)
    (project_dir / ".env").write_text("TOKEN=value\n", encoding="utf-8")

    result = check_unsafe_patterns(project_dir)

    assert not result.ok
    assert any(finding.code == "no-env-file" for finding in result.findings)


def test_unsafe_patterns_allows_ignored_venv_directory(tmp_path: Path) -> None:
    """A local `.venv` ignored by the generated `.gitignore` does not fail checks."""
    project_dir = _generated_project(tmp_path)
    (project_dir / ".venv").mkdir()

    result = check_unsafe_patterns(project_dir)

    assert result.ok


def test_unsafe_patterns_detects_unignored_runtime_artifact(tmp_path: Path) -> None:
    """Runtime artifact directories fail when they are not ignored."""
    project_dir = _generated_project(tmp_path)
    (project_dir / ".gitignore").write_text(".pytest_cache/\n", encoding="utf-8")
    (project_dir / ".venv").mkdir()

    result = check_unsafe_patterns(project_dir)

    assert not result.ok
    assert any(finding.code == "no-runtime-artifact" for finding in result.findings)


def test_project_health_detects_missing_agents_file(tmp_path: Path) -> None:
    """The project-health checker requires the shared agent instruction file."""
    project_dir = _generated_project(tmp_path)
    (project_dir / "AGENTS.md").unlink()

    result = check_project_health(project_dir)

    assert not result.ok
    assert any(finding.path == "AGENTS.md" for finding in result.findings)


def test_project_health_respects_disabled_docs_and_ci(tmp_path: Path) -> None:
    """Docs and CI paths are not required when disabled in config."""
    project_dir = _generated_project(tmp_path)
    _replace_text(project_dir / "scaffold-guard.toml", "docs = true", "docs = false")
    _replace_text(
        project_dir / "scaffold-guard.toml",
        "github_actions = true",
        "github_actions = false",
    )
    _remove_tree(project_dir / "docs")
    _remove_tree(project_dir / ".github")

    result = check_project_health(project_dir)

    assert result.ok


def test_project_health_detects_claude_wrapper_without_agents_reference(tmp_path: Path) -> None:
    """CLAUDE.md must reference the shared AGENTS.md instructions."""
    project_dir = _generated_project(tmp_path)
    (project_dir / "CLAUDE.md").write_text("# Claude Only\n", encoding="utf-8")

    result = check_project_health(project_dir)

    assert not result.ok
    assert any(finding.code == "claude-missing-agents-reference" for finding in result.findings)


def test_project_health_detects_invalid_cursor_rule_extension(tmp_path: Path) -> None:
    """Cursor rules must use `.mdc` files."""
    project_dir = _generated_project(tmp_path)
    bad_rule = project_dir / ".cursor/rules/foo.md"
    bad_rule.write_text("# Bad Rule\n", encoding="utf-8")

    result = check_project_health(project_dir)

    assert not result.ok
    assert any(finding.code == "cursor-rule-extension" for finding in result.findings)


def test_project_health_detects_cursor_rule_without_frontmatter(tmp_path: Path) -> None:
    """Cursor `.mdc` files must start with frontmatter."""
    project_dir = _generated_project(tmp_path)
    rule = project_dir / ".cursor/rules/python.mdc"
    rule.write_text("# Python Rules\n", encoding="utf-8")

    result = check_project_health(project_dir)

    assert not result.ok
    assert any(finding.code == "cursor-rule-frontmatter" for finding in result.findings)


def test_generated_files_detects_unresolved_agent_placeholder(tmp_path: Path) -> None:
    """Generated agent files must not retain Jinja placeholders."""
    project_dir = _generated_project(tmp_path)
    agents_path = project_dir / "AGENTS.md"
    agents_path.write_text(agents_path.read_text(encoding="utf-8") + "\n{{ missing }}\n")

    result = check_generated_files(project_dir)

    assert not result.ok
    assert any(finding.code == "unresolved-template-placeholder" for finding in result.findings)


def test_generated_files_detects_cursor_metadata_problems(tmp_path: Path) -> None:
    """Generated Cursor rules need delimited frontmatter and required keys."""
    project_dir = _generated_project(tmp_path)
    bad_frontmatter = project_dir / ".cursor/rules/python.mdc"
    bad_frontmatter.write_text("---\ndescription: Missing close\n# Body\n", encoding="utf-8")
    missing_metadata = project_dir / ".cursor/rules/testing.mdc"
    missing_metadata.write_text('---\nglobs: "tests/**/*.py"\n---\n# Testing\n', encoding="utf-8")

    result = check_generated_files(project_dir)
    codes = {finding.code for finding in result.findings}

    assert {"cursor-rule-frontmatter", "cursor-rule-metadata"}.issubset(codes)


def test_generated_files_detects_missing_readme_uv_and_ci_tools(tmp_path: Path) -> None:
    """Generated README and CI files must retain expected toolchain commands."""
    project_dir = _generated_project(tmp_path)
    (project_dir / "README.md").write_text("# Demo\n", encoding="utf-8")
    (project_dir / ".github/workflows/ci.yml").write_text(
        "name: CI\nrun: uv sync\n",
        encoding="utf-8",
    )

    result = check_generated_files(project_dir)
    codes = {finding.code for finding in result.findings}

    assert {"readme-missing-uv", "ci-missing-tool"}.issubset(codes)


def test_generated_files_respects_disabled_ci_tool_tokens(tmp_path: Path) -> None:
    """CI token checks only require enabled package tools."""
    project_dir = _generated_project(tmp_path)
    _replace_text(project_dir / "scaffold-guard.toml", "ruff = true", "ruff = false")
    _replace_text(project_dir / "scaffold-guard.toml", "mypy = true", "mypy = false")
    _replace_text(project_dir / "scaffold-guard.toml", "pyright = true", "pyright = false")
    (project_dir / ".github/workflows/ci.yml").write_text(
        "name: CI\nrun: uv sync && pytest && mkdocs\n",
        encoding="utf-8",
    )

    result = check_generated_files(project_dir)

    assert result.ok


def test_generated_files_allows_missing_optional_generated_files(tmp_path: Path) -> None:
    """Generated-file content checks skip absent README, CI, and Cursor rule paths."""
    project_dir = _generated_project(tmp_path)
    (project_dir / "README.md").unlink()
    _remove_tree(project_dir / ".github")
    _remove_tree(project_dir / ".cursor")
    _replace_text(
        project_dir / "scaffold-guard.toml",
        "github_actions = true",
        "github_actions = false",
    )

    result = check_generated_files(project_dir)

    assert result.ok


def test_config_consistency_detects_missing_config(tmp_path: Path) -> None:
    """Generated projects must keep scaffold-guard.toml."""
    project_dir = _generated_project(tmp_path)
    (project_dir / "scaffold-guard.toml").unlink()

    result = check_config_consistency(project_dir)

    assert not result.ok
    assert any(finding.code == "missing-scaffold-guard-config" for finding in result.findings)


def test_config_consistency_detects_agent_file_mismatches(tmp_path: Path) -> None:
    """Agent booleans must match generated adapter files."""
    project_dir = _generated_project(tmp_path)
    (project_dir / "CLAUDE.md").unlink()
    _remove_tree(project_dir / ".cursor")

    result = check_config_consistency(project_dir)
    paths = {finding.path for finding in result.findings}

    assert {"CLAUDE.md", ".cursor/rules"}.issubset(paths)


def test_config_consistency_detects_codex_mismatch(tmp_path: Path) -> None:
    """Codex-enabled config requires AGENTS.md."""
    project_dir = _generated_project(tmp_path)
    (project_dir / "AGENTS.md").unlink()

    result = check_config_consistency(project_dir)

    assert not result.ok
    assert any(finding.path == "AGENTS.md" for finding in result.findings)


def test_config_consistency_detects_python_and_coverage_mismatch(tmp_path: Path) -> None:
    """Configured Python and coverage settings must match pyproject.toml."""
    project_dir = _generated_project(tmp_path)
    _replace_text(project_dir / "pyproject.toml", ">=3.13", ">=3.12")
    _replace_text(project_dir / "pyproject.toml", "fail_under = 95", "fail_under = 90")

    result = check_config_consistency(project_dir)
    codes = {finding.code for finding in result.findings}

    assert {"python-min-config-mismatch", "coverage-config-mismatch"}.issubset(codes)


def test_config_consistency_warns_when_lockfile_is_older(tmp_path: Path) -> None:
    """Older lockfiles produce warnings without failing the check."""
    project_dir = _generated_project(tmp_path)
    lockfile = project_dir / "uv.lock"
    lockfile.write_text("version = 1\n", encoding="utf-8")
    pyproject = project_dir / "pyproject.toml"
    old_time = pyproject.stat().st_mtime - 100
    os.utime(lockfile, (old_time, old_time))

    result = check_config_consistency(project_dir)

    assert result.ok
    assert any(finding.severity == "warning" for finding in result.findings)


def test_config_consistency_skips_pyproject_comparisons_when_missing(tmp_path: Path) -> None:
    """Config consistency can still run when pyproject is absent."""
    project_dir = _generated_project(tmp_path)
    (project_dir / "pyproject.toml").unlink()

    result = check_config_consistency(project_dir)

    assert result.ok


def _generated_project(tmp_path: Path) -> Path:
    """Create a standard all-adapter generated project for checker tests."""
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


def _replace_text(path: Path, old: str, new: str) -> None:
    """Replace text in a UTF-8 file."""
    path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")


def _remove_tree(path: Path) -> None:
    """Remove a small generated directory tree."""
    if path.is_file():
        path.unlink()
        return
    for child in sorted(path.rglob("*"), reverse=True):
        if child.is_file():
            child.unlink()
        else:
            child.rmdir()
    if path.exists():
        path.rmdir()
