"""Tests for typed option models."""

from pathlib import Path

import pytest

from scaffold_guard.models import (
    AdapterSelection,
    InitOptions,
    TemplateSpec,
    adapter_selection_for_agent,
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
