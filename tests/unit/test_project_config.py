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
    assert options.ci == "github"
    assert options.ruff_enabled
    assert options.mypy_enabled
    assert options.pyright_enabled
    assert payload["name"] == "demo"
    assert payload["ci"] == "github"
    assert payload["agents"] == expected_flags
    assert payload["features"] == {
        "docs": True,
        "github_actions": True,
        "gitlab_ci": False,
    }
    assert payload["tools"] == {"ruff": True, "mypy": True, "pyright": True}


def test_generated_project_config_round_trips_gitlab_ci(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Generated config exposes GitLab CI selections."""
    project_dir = generated_project(tmp_path, ci="gitlab")

    config = load_generated_project_config(project_dir)
    options = config.to_init_options(dry_run=True, force=False)
    payload = config.to_json()

    assert config.ci == "gitlab"
    assert options.ci == "gitlab"
    assert not config.github_actions
    assert config.gitlab_ci
    assert payload["ci"] == "gitlab"
    assert payload["features"] == {
        "docs": True,
        "github_actions": False,
        "gitlab_ci": True,
    }


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


def test_generated_project_config_loads_legacy_package_profile(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    replace_text: Callable[[Path, str, str], None],
) -> None:
    """Existing package-profile configs are treated as canonical Python projects."""
    project_dir = generated_project(tmp_path)
    replace_text(project_dir / "scaffold-guard.toml", 'profile = "python"', 'profile = "package"')

    config = load_generated_project_config(project_dir)
    options = config.to_init_options(dry_run=True, force=False)

    assert config.profile == "python"
    assert config.python
    assert options.profile == "python"


def test_generated_project_config_loads_typescript_profile(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Generated config exposes TypeScript-only profile capabilities."""
    project_dir = generated_project(tmp_path, profile="typescript")

    config = load_generated_project_config(project_dir)
    payload = config.to_json()

    assert config.profile == "typescript"
    assert not config.python
    assert config.typescript
    assert not config.ruff
    assert payload["tools"] == {
        "ruff": False,
        "mypy": False,
        "pyright": False,
        "typescript": True,
        "typescript_strict": True,
        "biome": True,
        "vitest": True,
    }


def test_generated_project_config_loads_monorepo_profile(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Generated config exposes Python and TypeScript monorepo capabilities."""
    project_dir = generated_project(tmp_path, profile="monorepo")

    config = load_generated_project_config(project_dir)
    options = config.to_init_options(dry_run=True, force=False)

    assert config.profile == "monorepo"
    assert config.python
    assert config.typescript
    assert config.ruff
    assert config.mypy
    assert config.pyright
    assert config.typescript_strict
    assert config.biome
    assert config.vitest
    assert options.profile == "monorepo"
    assert options.python_enabled
    assert options.typescript_enabled
    assert options.typescript_strict_enabled
    assert options.biome_enabled
    assert options.vitest_enabled


def test_generated_project_config_round_trips_typescript_tool_selection(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Generated config exposes disabled TypeScript tool choices."""
    project_dir = generated_project(
        tmp_path,
        profile="typescript",
        typescript_strict=False,
        biome=False,
        vitest=False,
    )

    config = load_generated_project_config(project_dir)
    options = config.to_init_options(dry_run=True, force=False)
    payload = config.to_json()

    assert not config.typescript_strict
    assert not config.biome
    assert not config.vitest
    assert not options.typescript_strict_enabled
    assert not options.biome_enabled
    assert not options.vitest_enabled
    assert payload["tools"] == {
        "ruff": False,
        "mypy": False,
        "pyright": False,
        "typescript": True,
        "typescript_strict": False,
        "biome": False,
        "vitest": False,
    }


def test_generated_project_config_rejects_bad_profile_and_missing_coverage(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    replace_text: Callable[[Path, str, str], None],
) -> None:
    """Generated config validation reports unsupported profiles and missing integers."""
    project_dir = generated_project(tmp_path)
    config_path = project_dir / "scaffold-guard.toml"
    original = config_path.read_text(encoding="utf-8")

    replace_text(config_path, 'profile = "python"', 'profile = "application"')
    with pytest.raises(ProjectConfigError, match="Unsupported generated project profile"):
        load_generated_project_config(project_dir)

    config_path.write_text(
        original.replace("coverage_fail_under = 95\n", ""),
        encoding="utf-8",
    )
    with pytest.raises(ProjectConfigError, match="Missing required integer config value"):
        load_generated_project_config(project_dir)

    config_path.write_text(
        original.replace('ci = "github"', 'ci = "circle"'),
        encoding="utf-8",
    )
    with pytest.raises(ProjectConfigError, match="Unsupported generated project CI provider"):
        load_generated_project_config(project_dir)
