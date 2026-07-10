"""Tests for generated project configuration loading."""

from collections.abc import Callable
from pathlib import Path

import pytest

from scaffold_guard.models import AdapterSelection, AgentChoice
from scaffold_guard.project_config import (
    ProjectConfigError,
    load_generated_project_config,
)
from scaffold_guard.versions import PROJECT_FORMAT_VERSION


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
    assert config.adapters == tuple(name for name, enabled in expected_flags.items() if enabled)
    assert options.adapter_selection == config.adapters
    assert config.format_version == PROJECT_FORMAT_VERSION
    assert config.generated_with == "0.2.0"
    assert config.requires_scaffold_guard == ">=0.2.0"
    assert payload["features"] == {
        "docs": True,
        "github_actions": True,
        "gitlab_ci": False,
    }
    assert payload["tools"] == {
        "ruff": True,
        "ruff_mode": "strict",
        "mypy": True,
        "pyright": True,
        "python_typecheck": "strict",
        "python_typechecker": "mypy+pyright",
    }


@pytest.mark.parametrize(
    "selection",
    [
        (),
        ("codex", "claude"),
        ("codex", "cursor"),
        ("claude", "cursor"),
    ],
)
def test_generated_project_config_preserves_non_shorthand_adapter_sets(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    selection: tuple[AdapterSelection, ...],
) -> None:
    """Config booleans round-trip exactly even without an AgentChoice equivalent."""
    project_dir = generated_project(tmp_path, agent="all")
    config_path = project_dir / "scaffold-guard.toml"
    content = config_path.read_text(encoding="utf-8")
    for adapter in ("codex", "claude", "cursor"):
        enabled = "true" if adapter in selection else "false"
        content = content.replace(f"{adapter} = true", f"{adapter} = {enabled}")
    config_path.write_text(content, encoding="utf-8")

    config = load_generated_project_config(project_dir)
    options = config.to_init_options(dry_run=True, force=False)

    assert config.adapters == selection
    assert options.adapter_selection == selection


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
    assert payload["tools"] == {
        "ruff": False,
        "ruff_mode": "off",
        "mypy": False,
        "pyright": False,
        "python_typecheck": "off",
        "python_typechecker": "mypy+pyright",
    }


def test_generated_project_config_round_trips_python_quality_modes(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    replace_text: Callable[[Path, str, str], None],
) -> None:
    """Generated config exposes Python strictness and typechecker choices."""
    project_dir = generated_project(tmp_path, mypy=False, pyright=True)
    config_path = project_dir / "scaffold-guard.toml"
    replace_text(config_path, 'ruff_mode = "strict"', 'ruff_mode = "standard"')
    replace_text(config_path, 'python_typecheck = "strict"', 'python_typecheck = "standard"')
    replace_text(
        config_path, 'python_typechecker = "mypy+pyright"', 'python_typechecker = "pyright"'
    )

    config = load_generated_project_config(project_dir)
    options = config.to_init_options(dry_run=True, force=False)
    payload = config.to_json()

    assert config.ruff
    assert not config.mypy
    assert config.pyright
    assert config.ruff_mode == "standard"
    assert config.python_typecheck_mode == "standard"
    assert config.python_typechecker == "pyright"
    assert options.ruff_mode == "standard"
    assert options.python_typecheck_mode == "standard"
    assert options.python_typechecker == "pyright"
    assert payload["tools"] == {
        "ruff": True,
        "ruff_mode": "standard",
        "mypy": False,
        "pyright": True,
        "python_typecheck": "standard",
        "python_typechecker": "pyright",
    }


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


def test_generated_project_config_allows_missing_legacy_metadata(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Manifest-less 0.1.x project configuration remains loadable for upgrade."""
    project_dir = generated_project(tmp_path)
    config_path = project_dir / "scaffold-guard.toml"
    content = config_path.read_text(encoding="utf-8")
    legacy_content = content.split("\n[scaffold_guard]\n", maxsplit=1)[0].rstrip() + "\n"
    config_path.write_text(legacy_content, encoding="utf-8")

    config = load_generated_project_config(project_dir)

    assert config.format_version is None
    assert config.generated_with is None
    assert config.requires_scaffold_guard is None


def test_generated_project_config_allows_symlinked_project_root(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """A symlinked project-root argument remains loadable."""
    project_dir = generated_project(tmp_path)
    root_link = tmp_path / "project-link"
    root_link.symlink_to(project_dir, target_is_directory=True)

    config = load_generated_project_config(root_link)

    assert config.name == "demo"
    assert config.format_version == PROJECT_FORMAT_VERSION


def test_generated_project_config_rejects_symlinked_config_outside_root(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Config loading refuses a scaffold-guard.toml symlink outside the root."""
    project_dir = generated_project(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_config = outside / "scaffold-guard.toml"
    outside_config.write_text(
        (project_dir / "scaffold-guard.toml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (project_dir / "scaffold-guard.toml").unlink()
    (project_dir / "scaffold-guard.toml").symlink_to(outside_config)

    with pytest.raises(
        ProjectConfigError,
        match="symbolic links are not allowed below the project root",
    ):
        load_generated_project_config(project_dir)


def test_generated_project_config_rejects_symlinked_config_within_root(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Config loading treats an in-root scaffold-guard.toml symlink as a conflict."""
    project_dir = generated_project(tmp_path)
    config_path = project_dir / "scaffold-guard.toml"
    target = project_dir / "real-scaffold-guard.toml"
    config_path.rename(target)
    config_path.symlink_to(target.name)

    with pytest.raises(
        ProjectConfigError,
        match="symbolic links are not allowed below the project root",
    ):
        load_generated_project_config(project_dir)


def test_generated_project_config_rejects_empty_metadata_table(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """A present empty metadata table is malformed, not legacy absence."""
    project_dir = generated_project(tmp_path)
    config_path = project_dir / "scaffold-guard.toml"
    legacy_content = config_path.read_text(encoding="utf-8").split(
        "\n[scaffold_guard]\n", maxsplit=1
    )[0]
    config_path.write_text(f"{legacy_content}\n[scaffold_guard]\n", encoding="utf-8")

    with pytest.raises(ProjectConfigError, match="must not be empty"):
        load_generated_project_config(project_dir)


def test_generated_project_config_rejects_non_table_metadata_value(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """A scalar scaffold_guard key is malformed instead of legacy-compatible."""
    project_dir = generated_project(tmp_path)
    config_path = project_dir / "scaffold-guard.toml"
    content = config_path.read_text(encoding="utf-8")
    before_metadata, after_metadata = content.split("\n[scaffold_guard]\n", maxsplit=1)
    _metadata, after_metadata = after_metadata.split("\n[agents]\n", maxsplit=1)
    config_path.write_text(
        f'scaffold_guard = "custom"\n{before_metadata}\n[agents]\n{after_metadata}',
        encoding="utf-8",
    )

    with pytest.raises(ProjectConfigError, match="must be a table"):
        load_generated_project_config(project_dir)


def test_generated_project_config_rejects_incompatible_runtime_metadata(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    replace_text: Callable[[Path, str, str], None],
) -> None:
    """A stale global CLI cannot silently operate on a newer project format."""
    project_dir = generated_project(tmp_path)
    config_path = project_dir / "scaffold-guard.toml"
    replace_text(
        config_path,
        'requires_scaffold_guard = ">=0.2.0"',
        'requires_scaffold_guard = ">=99"',
    )

    with pytest.raises(ProjectConfigError, match="does not satisfy"):
        load_generated_project_config(project_dir)


def test_generated_project_config_rejects_unsupported_format_metadata(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    replace_text: Callable[[Path, str, str], None],
) -> None:
    """Unknown project formats fail before commands mutate files."""
    project_dir = generated_project(tmp_path)
    config_path = project_dir / "scaffold-guard.toml"
    replace_text(config_path, "format_version = 1", "format_version = 2")

    with pytest.raises(ProjectConfigError, match="Unsupported generated project format"):
        load_generated_project_config(project_dir)


def test_generated_project_config_rejects_unknown_reserved_metadata(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Unknown lifecycle metadata keys fail during ordinary project loading."""
    project_dir = generated_project(tmp_path)
    config_path = project_dir / "scaffold-guard.toml"
    content = config_path.read_text(encoding="utf-8").replace(
        "format_version = 1",
        'format_version = 1\nowner = "custom"',
    )
    config_path.write_text(content, encoding="utf-8")

    with pytest.raises(ProjectConfigError, match="unsupported key: owner"):
        load_generated_project_config(project_dir)


@pytest.mark.parametrize(
    ("original", "replacement", "message"),
    [
        ("codex = true", 'codex = "yes"', "must be a boolean"),
        ('ruff_mode = "strict"', 'ruff_mode = "maximum"', "quality mode"),
        (
            'python_typechecker = "mypy+pyright"',
            'python_typechecker = "pylance"',
            "typechecker",
        ),
    ],
)
def test_generated_project_config_rejects_malformed_present_options(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    replace_text: Callable[[Path, str, str], None],
    original: str,
    replacement: str,
    message: str,
) -> None:
    """Present invalid values do not silently fall back to legacy defaults."""
    project_dir = generated_project(tmp_path)
    replace_text(project_dir / "scaffold-guard.toml", original, replacement)

    with pytest.raises(ProjectConfigError, match=message):
        load_generated_project_config(project_dir)


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
        "ruff_mode": "off",
        "mypy": False,
        "pyright": False,
        "python_typecheck": "off",
        "python_typechecker": "mypy+pyright",
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
        "ruff_mode": "off",
        "mypy": False,
        "pyright": False,
        "python_typecheck": "off",
        "python_typechecker": "mypy+pyright",
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
