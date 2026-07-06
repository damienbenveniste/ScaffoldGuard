"""Tests for typed option models."""

from pathlib import Path

from agent_safe.models import InitOptions


def test_init_options_agent_flags_for_all() -> None:
    """The `all` adapter selection enables every concrete adapter."""
    options = InitOptions(
        target_dir=Path("demo"),
        project_slug="demo",
        package_name="demo",
        agent="all",
        profile="package",
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


def test_init_options_agent_flags_for_single_adapter() -> None:
    """A single adapter selection only enables its matching adapter."""
    options = InitOptions(
        target_dir=Path("demo"),
        project_slug="demo",
        package_name="demo",
        agent="claude",
        profile="package",
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
