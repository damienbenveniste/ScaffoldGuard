"""Tests for generated project configuration loading."""

from collections.abc import Callable
from pathlib import Path

import pytest

from scaffold_guard.models import AgentChoice
from scaffold_guard.project_config import (
    ProjectConfigError,
    load_generated_project_config,
)


@pytest.mark.parametrize(
    ("agent", "expected_choice", "expected_flags"),
    [
        ("codex", "codex", {"codex": True, "claude": False, "cursor": False}),
        ("claude", "claude", {"codex": False, "claude": True, "cursor": False}),
        ("cursor", "cursor", {"codex": False, "claude": False, "cursor": True}),
        ("all", "all", {"codex": True, "claude": True, "cursor": True}),
    ],
)
def test_generated_project_config_round_trips_agent_selection(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    agent: AgentChoice,
    expected_choice: AgentChoice,
    expected_flags: dict[str, bool],
) -> None:
    """Generated config exposes the fields needed by V1 commands."""
    project_dir = generated_project(tmp_path, agent=agent)

    config = load_generated_project_config(project_dir)
    options = config.to_init_options(dry_run=True, force=False)
    payload = config.to_json()

    assert config.agent_choice == expected_choice
    assert options.agent == expected_choice
    assert options.target_dir == project_dir
    assert options.package_name == "demo"
    assert options.ruff_enabled
    assert options.mypy_enabled
    assert options.pyright_enabled
    assert payload["name"] == "demo"
    assert payload["agents"] == expected_flags
    assert payload["tools"] == {"ruff": True, "mypy": True, "pyright": True}


def test_generated_project_config_round_trips_tool_selection(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Generated config exposes disabled quality-tool choices."""
    project_dir = generated_project(tmp_path, ruff=False, mypy=False, pyright=False)

    config = load_generated_project_config(project_dir)
    options = config.to_init_options(dry_run=True, force=False)
    payload = config.to_json()

    assert not config.ruff
    assert not config.mypy
    assert not config.pyright
    assert not options.ruff_enabled
    assert not options.mypy_enabled
    assert not options.pyright_enabled
    assert payload["tools"] == {"ruff": False, "mypy": False, "pyright": False}


def test_generated_project_config_rejects_missing_required_fields(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Generated-project-only commands require a complete scaffold-guard.toml."""
    project_dir = generated_project(tmp_path)
    (project_dir / "scaffold-guard.toml").write_text(
        "[project]\nname = 'demo'\n",
        encoding="utf-8",
    )

    with pytest.raises(ProjectConfigError, match="Missing required string config value"):
        load_generated_project_config(project_dir)


def test_generated_project_config_loads_minimal_profile(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Generated config supports the guardrails-only minimal profile."""
    project_dir = generated_project(tmp_path, profile="minimal")

    config = load_generated_project_config(project_dir)
    options = config.to_init_options(dry_run=True, force=False)

    assert config.profile == "minimal"
    assert options.profile == "minimal"
    assert not (project_dir / "pyproject.toml").exists()
    assert not (project_dir / "src").exists()


def test_generated_project_config_rejects_bad_profile_and_missing_coverage(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    replace_text: Callable[[Path, str, str], None],
) -> None:
    """Generated config validation reports unsupported profiles and missing integers."""
    project_dir = generated_project(tmp_path)
    config_path = project_dir / "scaffold-guard.toml"
    original = config_path.read_text(encoding="utf-8")

    replace_text(config_path, 'profile = "package"', 'profile = "application"')
    with pytest.raises(ProjectConfigError, match="Unsupported generated project profile"):
        load_generated_project_config(project_dir)

    config_path.write_text(
        original.replace("coverage_fail_under = 95\n", ""),
        encoding="utf-8",
    )
    with pytest.raises(ProjectConfigError, match="Missing required integer config value"):
        load_generated_project_config(project_dir)
