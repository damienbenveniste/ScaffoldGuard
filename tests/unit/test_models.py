"""Tests for typed option models."""

from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from scaffold_guard.models import (
    AdapterSelection,
    InitOptions,
    MonorepoLayout,
    MonorepoWorkspaces,
    TemplateSpec,
    WorkspacePath,
    adapter_selection_for_agent,
    monorepo_workspaces,
    normalize_adapter_selection,
    normalize_profile_choice,
)


def test_init_options_agent_flags_for_all() -> None:
    """The `all` adapter selection enables every concrete adapter."""
    options = InitOptions(
        target_dir=Path("demo"),
        project_slug="demo",
        package_name="demo",
        agent="all",
        profile="python",
        license="MIT",
        python_min="3.13",
        coverage=95,
        ci="github",
        docs_enabled=True,
        dry_run=False,
        force=False,
    )

    assert options.codex_enabled
    assert options.claude_enabled
    assert options.cursor_enabled
    assert options.adapter_selection == ("codex", "claude", "cursor")


def test_init_options_agent_flags_for_single_adapter() -> None:
    """A single adapter selection only enables its matching adapter."""
    options = InitOptions(
        target_dir=Path("demo"),
        project_slug="demo",
        package_name="demo",
        agent="claude",
        profile="python",
        license="MIT",
        python_min="3.13",
        coverage=95,
        ci="github",
        docs_enabled=True,
        dry_run=False,
        force=False,
    )

    assert not options.codex_enabled
    assert options.claude_enabled
    assert not options.cursor_enabled
    assert options.adapter_selection == ("claude",)


@pytest.mark.parametrize(
    "selection",
    [
        ("codex", "claude"),
        ("codex", "cursor"),
        ("claude", "cursor"),
    ],
)
def test_init_options_preserves_exact_adapter_selection(
    selection: tuple[AdapterSelection, ...],
) -> None:
    """Exact adapter selections do not collapse to the legacy CLI shorthand."""
    options = InitOptions(
        target_dir=Path("demo"),
        project_slug="demo",
        package_name="demo",
        agent="codex",
        profile="python",
        license="MIT",
        python_min="3.13",
        coverage=95,
        ci="github",
        docs_enabled=True,
        dry_run=False,
        force=False,
        adapter_selection=selection,
    )

    assert options.adapter_selection == selection
    assert options.codex_enabled == ("codex" in selection)
    assert options.claude_enabled == ("claude" in selection)
    assert options.cursor_enabled == ("cursor" in selection)


def test_init_options_preserves_empty_adapter_selection() -> None:
    """Config-driven rendering can preserve all adapter booleans as false."""
    options = InitOptions(
        target_dir=Path("demo"),
        project_slug="demo",
        package_name="demo",
        agent="codex",
        profile="python",
        license="MIT",
        python_min="3.13",
        coverage=95,
        ci="github",
        docs_enabled=True,
        dry_run=False,
        force=False,
        adapter_selection=(),
    )

    assert options.adapter_selection == ()
    assert not options.codex_enabled
    assert not options.claude_enabled
    assert not options.cursor_enabled


def test_adapter_selection_for_agent_expands_cli_shorthand() -> None:
    """CLI agent shorthand expands to exact adapter selections."""
    assert adapter_selection_for_agent("codex") == ("codex",)
    assert adapter_selection_for_agent("all") == ("codex", "claude", "cursor")


def test_template_spec_requires_stable_id_and_lifecycle() -> None:
    """Template specs carry the lifecycle fields used by manifests."""
    spec = TemplateSpec(
        template_id="package/AGENTS.md",
        template_name="package/AGENTS.md.j2",
        destination="AGENTS.md",
        lifecycle="managed",
    )

    assert spec.template_id == "package/AGENTS.md"
    assert spec.lifecycle == "managed"


def test_normalize_profile_choice_accepts_legacy_package_alias() -> None:
    """Legacy package profile values normalize to the canonical Python profile."""
    assert normalize_profile_choice("package") == "python"


def test_model_normalizers_reject_unknown_values() -> None:
    """Unknown persisted model values fail instead of being guessed."""
    with pytest.raises(ValueError, match="Unsupported project profile"):
        normalize_profile_choice("rust")
    with pytest.raises(ValueError, match="Unsupported agent adapter"):
        normalize_adapter_selection(cast("tuple[AdapterSelection, ...]", ("unknown",)))
    with pytest.raises(ValueError, match="Unsupported monorepo layout"):
        monorepo_workspaces(cast("MonorepoLayout", "unknown"))


@pytest.mark.parametrize(
    "path",
    [
        "",
        ".",
        "/absolute",
        "../escape",
        "nested/../escape",
        ".git/worktree",
        "src/./python",
        "services/my api",
        "services/$(whoami)",
        "services/api;echo",
        "C:/workspace",
        "services\\api",
    ],
)
def test_workspace_path_rejects_unsafe_relative_directories(path: str) -> None:
    """Workspace paths reject traversal, control roots, and shell-unsafe segments."""
    with pytest.raises(ValueError, match=r"must|Invalid"):
        WorkspacePath.parse(path, field_name="python_workspace")


def test_workspace_path_direct_construction_rejects_empty_path() -> None:
    """Direct typed construction enforces the same nonempty invariant as parsing."""
    with pytest.raises(ValueError, match="must not be empty"):
        WorkspacePath(Path())


def test_monorepo_workspaces_define_fixed_and_custom_layouts() -> None:
    """Typed monorepo layouts carry exact validated workspace paths."""
    application = monorepo_workspaces("application")
    library = monorepo_workspaces("library")
    custom = monorepo_workspaces(
        "custom",
        python_workspace=WorkspacePath.parse("services/backend", field_name="python_workspace"),
        typescript_workspace=WorkspacePath.parse(
            "frontends/browser",
            field_name="typescript_workspace",
        ),
    )

    assert application.python.as_posix() == "apps/api"
    assert application.typescript.as_posix() == "apps/web"
    assert library.python.as_posix() == "packages/core"
    assert library.typescript.as_posix() == "packages/client"
    assert custom.layout == "custom"


def test_monorepo_workspaces_reject_overlap_and_fixed_layout_overrides() -> None:
    """Language workspaces must be disjoint and fixed layouts remain truthful."""
    with pytest.raises(ValueError, match="must not overlap"):
        MonorepoWorkspaces(
            layout="custom",
            python=WorkspacePath(Path("workspaces")),
            typescript=WorkspacePath(Path("workspaces/web")),
        )
    with pytest.raises(ValueError, match="must be different"):
        MonorepoWorkspaces(
            layout="custom",
            python=WorkspacePath(Path("workspaces/python")),
            typescript=WorkspacePath(Path("workspaces/python")),
        )
    with pytest.raises(ValueError, match="application monorepo layout requires"):
        monorepo_workspaces(
            "application",
            python_workspace=WorkspacePath(Path("services/api")),
        )


def test_init_options_default_monorepo_layout_is_application() -> None:
    """Direct monorepo options normalize to the public default layout."""
    options = InitOptions(
        target_dir=Path("demo"),
        project_slug="demo",
        package_name="demo",
        agent="codex",
        profile="monorepo",
        license="MIT",
        python_min="3.13",
        coverage=95,
        ci="github",
        docs_enabled=False,
        dry_run=False,
        force=False,
    )

    assert options.monorepo_layout == "application"
    assert options.python_workspace == WorkspacePath(Path("apps/api"))
    assert options.typescript_workspace == WorkspacePath(Path("apps/web"))


def test_init_options_rejects_monorepo_fields_for_other_profiles() -> None:
    """Monorepo workspace state cannot leak into another generated profile."""
    options = InitOptions(
        target_dir=Path("demo"),
        project_slug="demo",
        package_name="demo",
        agent="codex",
        profile="python",
        license="MIT",
        python_min="3.13",
        coverage=95,
        ci="github",
        docs_enabled=True,
        dry_run=False,
        force=False,
    )

    with pytest.raises(ValueError, match="require the monorepo profile"):
        replace(options, monorepo_layout="application")
