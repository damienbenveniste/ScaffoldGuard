"""Tests for generated agent rule compilation."""

import json
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
    assert Path(".codex/config.toml") in selected_files
    assert Path(".codex/hooks.json") in selected_files
    assert Path(".codex/agents/implementation-worker.toml") in selected_files
    assert Path(".codex/agents/docs-worker.toml") in selected_files
    assert Path(".codex/agents/reviewer.toml") in selected_files
    assert Path(".codex/hooks/workflow-evidence.sh") in selected_files
    assert Path(".codex/rules/validation.rules") in selected_files
    assert Path(".cursor/rules/python.mdc") in selected_files
    assert agents_path.read_text(encoding="utf-8") == initial_content
    assert agents_path.read_text(encoding="utf-8").count(GENERATED_MARKER) == 1
    git_rules = (project_dir / ".codex/rules/git.rules").read_text(encoding="utf-8")
    assert 'pattern = ["uv", "run", "scaffold-guard", "publish"]' in git_rules
    assert 'pattern = ["scaffold-guard", "publish"]' not in git_rules
    assert 'decision = "prompt"' not in git_rules


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

    assert summary.files == (
        Path("AGENTS.md"),
        Path(".codex/config.toml"),
        Path(".codex/hooks.json"),
        Path(".codex/agents/implementation-worker.toml"),
        Path(".codex/agents/docs-worker.toml"),
        Path(".codex/agents/reviewer.toml"),
        Path(".codex/hooks/workflow-evidence.sh"),
        Path(".codex/rules/git.rules"),
        Path(".codex/rules/validation.rules"),
    )
    assert GENERATED_MARKER in agents_path.read_text(encoding="utf-8")


def test_compile_rules_refuses_marker_preserving_markdown_edits_without_force(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """A retained generated Markdown marker is not enough to allow overwrite."""
    project_dir = generated_project(tmp_path)
    agents_path = project_dir / "AGENTS.md"
    agents_path.write_text(
        agents_path.read_text(encoding="utf-8").replace(
            "## Project Orientation",
            "## Local Project Orientation",
        ),
        encoding="utf-8",
    )

    with pytest.raises(FileExistsError, match=r"AGENTS\.md"):
        compile_rules(project_dir, agent="codex", dry_run=False, force=False)


def test_compile_rules_refuses_invalid_bytes_with_generated_marker_without_force(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Generated marker bytes do not allow non-UTF-8 content drift."""
    project_dir = generated_project(tmp_path)
    agents_path = project_dir / "AGENTS.md"
    agents_path.write_bytes(agents_path.read_bytes() + b"\xff")

    with pytest.raises(FileExistsError, match=r"AGENTS\.md"):
        compile_rules(project_dir, agent="codex", dry_run=False, force=False)


def test_compile_rules_refuses_json_hooks_edits_with_generated_status_without_force(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """A retained generated JSON status phrase is not enough to allow overwrite."""
    project_dir = generated_project(tmp_path)
    hooks_path = project_dir / ".codex/hooks.json"
    hooks_path.write_text(
        hooks_path.read_text(encoding="utf-8").replace(
            "scaffold-guard generated: checking project policy after file edits",
            "scaffold-guard generated: checking project policy after local edits",
        ),
        encoding="utf-8",
    )

    with pytest.raises(FileExistsError, match=r"\.codex/hooks\.json"):
        compile_rules(project_dir, agent="codex", dry_run=False, force=False)


def test_compile_rules_allows_exact_existing_content_without_force(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Exactly rendered files remain idempotent without requiring --force."""
    project_dir = generated_project(tmp_path)
    selected_files = selected_agent_files(load_generated_project_config(project_dir))
    initial_contents = {
        path: (project_dir / path).read_text(encoding="utf-8") for path in selected_files
    }

    summary = compile_rules(project_dir, agent="all", dry_run=False, force=False)

    assert summary.files == selected_files
    assert {
        path: (project_dir / path).read_text(encoding="utf-8") for path in selected_files
    } == initial_contents


def test_compile_rules_force_replaces_changed_generated_content(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """--force preserves the explicit replacement path for changed generated files."""
    project_dir = generated_project(tmp_path)
    agents_path = project_dir / "AGENTS.md"
    expected_content = agents_path.read_text(encoding="utf-8")
    agents_path.write_text(
        expected_content.replace("## Project Orientation", "## Local Project Orientation"),
        encoding="utf-8",
    )

    summary = compile_rules(project_dir, agent="codex", dry_run=False, force=True)

    assert Path("AGENTS.md") in summary.files
    assert agents_path.read_text(encoding="utf-8") == expected_content


def test_compile_rules_can_plan_missing_selected_adapter_files(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Rule compilation can add selected adapter files that are not present yet."""
    project_dir = generated_project(tmp_path, agent="codex")

    summary = compile_rules(project_dir, agent="claude", dry_run=True, force=False)

    assert Path("CLAUDE.md") in summary.files
    assert not (project_dir / "CLAUDE.md").exists()


def test_compile_rules_selects_typescript_adapter_files(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """TypeScript projects regenerate TypeScript adapter rules without Python rules."""
    project_dir = generated_project(tmp_path, profile="typescript")
    selected_files = selected_agent_files(load_generated_project_config(project_dir))

    assert Path(".claude/rules/typescript.md") in selected_files
    assert Path(".cursor/rules/typescript.mdc") in selected_files
    assert Path(".claude/rules/python.md") not in selected_files
    assert Path(".cursor/rules/python.mdc") not in selected_files


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
            RenderedFile(path=Path(".codex/config.toml"), content='sandbox_mode = "read-only"\n'),
            RenderedFile(
                path=Path(".codex/hooks.json"),
                content='{"hooks": {"PostToolUse": []}}\n',
            ),
            RenderedFile(path=Path(".codex/hooks/workflow-evidence.sh"), content="echo evidence\n"),
            RenderedFile(path=Path(".codex/rules/git.rules"), content="prefix_rule(\n)\n"),
            RenderedFile(
                path=Path(".cursor/rules/python.mdc"),
                content='---\ndescription: Python\nglobs: "src/**/*.py"\n---\n# Python\n',
            ),
        )

    monkeypatch.setattr(compile_rules_module, "render_package_files", fake_render_package_files)

    summary = compile_rules(project_dir, agent="all", dry_run=False, force=True)
    claude_content = (project_dir / "CLAUDE.md").read_text(encoding="utf-8")
    codex_config = (project_dir / ".codex/config.toml").read_text(encoding="utf-8")
    codex_hooks = (project_dir / ".codex/hooks.json").read_text(encoding="utf-8")
    codex_hook_script = (project_dir / ".codex/hooks/workflow-evidence.sh").read_text(
        encoding="utf-8"
    )
    codex_rules = (project_dir / ".codex/rules/git.rules").read_text(encoding="utf-8")
    cursor_content = (project_dir / ".cursor/rules/python.mdc").read_text(encoding="utf-8")

    assert summary.files == (
        Path("CLAUDE.md"),
        Path(".codex/config.toml"),
        Path(".codex/hooks.json"),
        Path(".codex/hooks/workflow-evidence.sh"),
        Path(".codex/rules/git.rules"),
        Path(".cursor/rules/python.mdc"),
    )
    assert claude_content.startswith(f"{GENERATED_MARKER}\n\n@AGENTS.md")
    assert codex_config.startswith("# generated by scaffold-guard")
    assert codex_hook_script.startswith("# generated by scaffold-guard")
    assert codex_rules.startswith("# generated by scaffold-guard")
    assert json.loads(codex_hooks) == {"hooks": {"PostToolUse": []}}
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
