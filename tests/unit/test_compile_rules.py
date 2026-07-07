"""Tests for generated agent rule compilation."""

from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from typer.testing import CliRunner

import scaffold_guard.compile_rules as compile_rules_module
from scaffold_guard.cli import app
from scaffold_guard.compile_rules import (
    GENERATED_MARKER,
    compile_rules,
    selected_agent_files,
)
from scaffold_guard.models import InitOptions
from scaffold_guard.project_config import load_generated_project_config
from scaffold_guard.scaffold import RenderedFile

SUCCESS = 0
CONFIG_ERROR = 2


def test_compile_rules_is_idempotent_and_reports_selected_files(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Rule compilation can safely refresh generated agent instruction files."""
    project_dir = generated_project(tmp_path)
    agents_path = project_dir / "AGENTS.md"
    initial_content = agents_path.read_text(encoding="utf-8")

    summary = compile_rules(project_dir, agent="all", dry_run=False, force=False)
    second_summary = compile_rules(project_dir, agent="all", dry_run=False, force=False)
    payload = summary.to_json()
    files = cast("list[str]", payload["files"])
    selected_files = selected_agent_files(load_generated_project_config(project_dir))

    assert not summary.dry_run
    assert Path("AGENTS.md") in summary.files
    assert Path("AGENTS.md") in second_summary.files
    assert "AGENTS.md" in files
    assert Path(".cursor/rules/python.mdc") in selected_files
    assert agents_path.read_text(encoding="utf-8") == initial_content
    assert agents_path.read_text(encoding="utf-8").count(GENERATED_MARKER) == 1


def test_compile_rules_refuses_manual_files_without_force(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Manual instruction files are protected unless the user opts into overwrite."""
    project_dir = generated_project(tmp_path)
    agents_path = project_dir / "AGENTS.md"
    agents_path.write_text("# Manual Rules\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="without --force"):
        compile_rules(project_dir, agent="codex", dry_run=False, force=False)

    summary = compile_rules(project_dir, agent="codex", dry_run=False, force=True)

    assert summary.files == (Path("AGENTS.md"),)
    assert GENERATED_MARKER in agents_path.read_text(encoding="utf-8")


def test_compile_rules_can_plan_missing_selected_adapter_files(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Rule compilation can add selected adapter files that are not present yet."""
    project_dir = generated_project(tmp_path, agent="codex")

    summary = compile_rules(project_dir, agent="claude", dry_run=True, force=False)

    assert Path("CLAUDE.md") in summary.files
    assert not (project_dir / "CLAUDE.md").exists()


def test_compile_rules_marks_unmarked_rendered_files(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rule compilation adds generated markers to unmarked rendered outputs."""
    project_dir = generated_project(tmp_path)

    def fake_render_package_files(options: InitOptions) -> tuple[RenderedFile, ...]:
        assert options.agent == "all"
        return (
            RenderedFile(path=Path("CLAUDE.md"), content="@AGENTS.md\n"),
            RenderedFile(
                path=Path(".cursor/rules/python.mdc"),
                content='---\ndescription: Python\nglobs: "src/**/*.py"\n---\n# Python\n',
            ),
        )

    monkeypatch.setattr(compile_rules_module, "render_package_files", fake_render_package_files)

    summary = compile_rules(project_dir, agent="all", dry_run=False, force=True)
    claude_content = (project_dir / "CLAUDE.md").read_text(encoding="utf-8")
    cursor_content = (project_dir / ".cursor/rules/python.mdc").read_text(encoding="utf-8")

    assert summary.files == (Path("CLAUDE.md"), Path(".cursor/rules/python.mdc"))
    assert claude_content.startswith(f"{GENERATED_MARKER}\n\n@AGENTS.md")
    assert f"---\n{GENERATED_MARKER}\n\n# Python" in cursor_content


def test_compile_rules_cli_dry_run_leaves_files_unchanged(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """The public compile-rules dry-run path reports planned writes only."""
    project_dir = generated_project(tmp_path)
    agents_path = project_dir / "AGENTS.md"
    agents_path.write_text("# Manual Rules\n", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "compile-rules",
            "--path",
            str(project_dir),
            "--agent",
            "codex",
            "--dry-run",
            "--force",
        ],
    )

    assert result.exit_code == SUCCESS, result.output
    assert "Planned agent instruction files" in result.output
    assert agents_path.read_text(encoding="utf-8") == "# Manual Rules\n"


def test_compile_rules_cli_reports_configuration_errors(tmp_path: Path) -> None:
    """The public compile-rules command reports missing generated config distinctly."""
    result = CliRunner().invoke(app, ["compile-rules", "--path", str(tmp_path)])

    assert result.exit_code == CONFIG_ERROR
    assert "Generated project config is missing" in result.output
