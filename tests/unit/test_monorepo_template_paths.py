"""Tests for configurable workspace paths in current monorepo templates."""

import json
import tomllib
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import pytest

from scaffold_guard.models import MonorepoLayout, WorkspacePath
from scaffold_guard.renderer import TemplateRenderer
from scaffold_guard.scaffold import (
    build_init_options,
    render_package_files,
    with_monorepo_layout,
)

MONOREPO_TEMPLATES: tuple[tuple[str, bool, bool], ...] = (
    ("monorepo/AGENTS.md.j2", True, True),
    ("monorepo/README.md.j2", True, True),
    ("monorepo/biome.json.j2", False, True),
    ("monorepo/github/workflows/ci.yml.j2", True, False),
    ("monorepo/gitignore.j2", False, True),
    ("monorepo/gitlab-ci.yml.j2", True, False),
    ("monorepo/package.json.j2", False, True),
    ("monorepo/pyproject.toml.j2", True, False),
    ("monorepo/pyrightconfig.json.j2", True, False),
    ("monorepo/scaffold-guard.toml.j2", True, True),
    ("agents/claude/rules/typescript.md.j2", False, True),
    ("agents/codex/rules/validation.rules.j2", True, False),
    ("agents/cursor/rules/typescript.mdc.j2", False, True),
)

LAYOUTS: tuple[tuple[MonorepoLayout, str, str], ...] = (
    ("application", "apps/api", "apps/web"),
    ("library", "packages/core", "packages/client"),
    ("custom", "services/platform-api", "clients/browser-sdk"),
    ("legacy", "packages/python", "packages/typescript"),
)


def _context(
    *,
    monorepo_layout: str,
    python_workspace: str,
    typescript_workspace: str,
) -> Mapping[str, object]:
    return {
        "project_slug": "demo-project",
        "package_name": "demo_project",
        "typescript_package_name": "demo-project",
        "profile": "monorepo",
        "license": "MIT",
        "python_min": "3.13",
        "generated_project_minimum_version": "0.3.0",
        "ruff_target_version": "py313",
        "coverage": 95,
        "ci_provider": "github",
        "configured_tools": "Ruff, mypy, Pyright, pytest, and coverage",
        "use_ruff": True,
        "use_mypy": True,
        "use_pyright": True,
        "ruff_mode": "strict",
        "python_typecheck_mode": "strict",
        "python_typechecker": "both",
        "use_ruff_strict": True,
        "use_python_typecheck_strict": True,
        "use_typescript_strict": True,
        "use_biome": True,
        "use_vitest": True,
        "use_python": True,
        "use_typescript": True,
        "ruff_enabled": "true",
        "mypy_enabled": "true",
        "pyright_enabled": "true",
        "typescript_strict_enabled": "true",
        "biome_enabled": "true",
        "vitest_enabled": "true",
        "codex_enabled": "true",
        "claude_enabled": "true",
        "cursor_enabled": "true",
        "github_actions_enabled": "true",
        "gitlab_ci_enabled": "false",
        "scaffold_guard_version": "0.3.0",
        "generated_project_minimum_specifier": ">=0.3.0",
        "project_format_version": 2,
        "docs_enabled": "false",
        "monorepo_layout": monorepo_layout,
        "python_workspace": python_workspace,
        "typescript_workspace": typescript_workspace,
    }


@pytest.mark.parametrize(
    ("monorepo_layout", "python_workspace", "typescript_workspace"),
    LAYOUTS,
)
def test_current_monorepo_templates_render_configured_workspace_paths(
    monorepo_layout: str,
    python_workspace: str,
    typescript_workspace: str,
) -> None:
    """Every current path-bearing template renders the selected workspaces."""
    renderer = TemplateRenderer()
    context = _context(
        monorepo_layout=monorepo_layout,
        python_workspace=python_workspace,
        typescript_workspace=typescript_workspace,
    )

    for template_name, uses_python, uses_typescript in MONOREPO_TEMPLATES:
        rendered = renderer.render(template_name, context)

        if uses_python:
            assert python_workspace in rendered
        if uses_typescript:
            assert typescript_workspace in rendered
        if monorepo_layout != "legacy":
            assert "packages/python" not in rendered
            assert "packages/typescript" not in rendered


@pytest.mark.parametrize(
    ("monorepo_layout", "python_workspace", "typescript_workspace"),
    LAYOUTS,
)
def test_monorepo_structured_templates_remain_parseable(
    monorepo_layout: str,
    python_workspace: str,
    typescript_workspace: str,
) -> None:
    """Configured nested and hyphenated paths remain valid JSON and TOML."""
    renderer = TemplateRenderer()
    context = _context(
        monorepo_layout=monorepo_layout,
        python_workspace=python_workspace,
        typescript_workspace=typescript_workspace,
    )

    package_json = json.loads(renderer.render("monorepo/package.json.j2", context))
    biome_json = json.loads(renderer.render("monorepo/biome.json.j2", context))
    pyright_json = json.loads(renderer.render("monorepo/pyrightconfig.json.j2", context))
    pyproject = tomllib.loads(renderer.render("monorepo/pyproject.toml.j2", context))
    scaffold_config = tomllib.loads(renderer.render("monorepo/scaffold-guard.toml.j2", context))

    assert package_json["workspaces"] == [typescript_workspace]
    assert biome_json["files"]["includes"][0] == f"{typescript_workspace}/**"
    assert pyright_json["include"][0] == f"{python_workspace}/src"
    assert pyproject["tool"]["pytest"]["ini_options"]["testpaths"] == [f"{python_workspace}/tests"]
    assert scaffold_config["monorepo"] == {
        "layout": monorepo_layout,
        "python_workspace": python_workspace,
        "typescript_workspace": typescript_workspace,
    }


@pytest.mark.parametrize(
    ("monorepo_layout", "python_workspace", "typescript_workspace"),
    LAYOUTS,
)
def test_monorepo_layouts_render_to_configured_destinations_with_stable_ids(
    tmp_path: Path,
    monorepo_layout: MonorepoLayout,
    python_workspace: str,
    typescript_workspace: str,
) -> None:
    """Configured layouts relocate outputs without changing template identity."""
    base_options = build_init_options(
        "demo-project",
        base_dir=tmp_path,
        agent="all",
        profile="monorepo",
        license_name="MIT",
        python_min="3.13",
        coverage=95,
        ci="github",
        dry_run=True,
        force=False,
    )
    if monorepo_layout == "legacy":
        options = replace(
            base_options,
            monorepo_layout="legacy",
            python_workspace=WorkspacePath(Path(python_workspace)),
            typescript_workspace=WorkspacePath(Path(typescript_workspace)),
        )
    else:
        options = with_monorepo_layout(
            base_options,
            layout=monorepo_layout,
            python_workspace=python_workspace if monorepo_layout == "custom" else None,
            typescript_workspace=(typescript_workspace if monorepo_layout == "custom" else None),
        )
    rendered_by_path = {rendered.path: rendered for rendered in render_package_files(options)}

    python_core = rendered_by_path[Path(f"{python_workspace}/src/demo_project/core.py")]
    typescript_source = rendered_by_path[Path(f"{typescript_workspace}/src/index.ts")]

    assert python_core.template_id == "monorepo/packages/python/src/package/core.py"
    assert typescript_source.template_id == "monorepo/packages/typescript/src/index.ts"
    scaffold_config = tomllib.loads(rendered_by_path[Path("scaffold-guard.toml")].content)
    assert scaffold_config["monorepo"] == {
        "layout": monorepo_layout,
        "python_workspace": python_workspace,
        "typescript_workspace": typescript_workspace,
    }
