"""Small TOML and generated-project config helpers."""

import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from scaffold_guard.models import normalize_profile_choice


def load_toml(path: Path) -> Mapping[str, object]:
    """Load a TOML file as a nested object mapping."""
    return cast("Mapping[str, object]", tomllib.loads(path.read_text(encoding="utf-8")))


def table_value(config: Mapping[str, object], key: str) -> Mapping[str, object]:
    """Return a nested TOML table, or an empty mapping when absent."""
    value = config.get(key)
    if isinstance(value, Mapping):
        return cast("Mapping[str, object]", value)
    return {}


def str_value(config: Mapping[str, object], key: str) -> str | None:
    """Return a string TOML value when present."""
    value = config.get(key)
    return value if isinstance(value, str) else None


def int_value(config: Mapping[str, object], key: str) -> int | None:
    """Return an integer TOML value when present."""
    value = config.get(key)
    return value if isinstance(value, int) else None


def bool_value(config: Mapping[str, object], key: str, *, default: bool) -> bool:
    """Return a boolean TOML value, or `default` when absent."""
    value = config.get(key)
    return value if isinstance(value, bool) else default


def load_scaffold_guard_toml(root: Path) -> Mapping[str, object]:
    """Load `scaffold-guard.toml`, returning an empty mapping when absent."""
    config_path = root / "scaffold-guard.toml"
    if not config_path.exists():
        return {}
    return load_toml(config_path)


def docs_enabled(root: Path) -> bool:
    """Return whether generated docs are enabled for a project."""
    config = load_scaffold_guard_toml(root)
    features = table_value(config, "features")
    return bool_value(features, "docs", default=True)


def ci_enabled(root: Path) -> bool:
    """Return whether generated CI is enabled for a project."""
    return github_actions_enabled(root) or gitlab_ci_enabled(root)


def github_actions_enabled(root: Path) -> bool:
    """Return whether generated GitHub Actions CI is enabled for a project."""
    config = load_scaffold_guard_toml(root)
    features = table_value(config, "features")
    return bool_value(features, "github_actions", default=ci_provider(root) == "github")


def gitlab_ci_enabled(root: Path) -> bool:
    """Return whether generated GitLab CI is enabled for a project."""
    config = load_scaffold_guard_toml(root)
    features = table_value(config, "features")
    return bool_value(features, "gitlab_ci", default=ci_provider(root) == "gitlab")


def ci_provider(root: Path) -> str:
    """Return the configured CI provider, defaulting older configs to GitHub."""
    config = load_scaffold_guard_toml(root)
    project = table_value(config, "project")
    features = table_value(config, "features")
    provider = str_value(project, "ci")
    if provider in {"github", "gitlab"}:
        return provider
    if bool_value(features, "gitlab_ci", default=False):
        return "gitlab"
    return "github"


def project_profile(root: Path) -> str:
    """Return the canonical project profile, defaulting legacy configs to Python."""
    config = load_scaffold_guard_toml(root)
    project = table_value(config, "project")
    profile = str_value(project, "profile") or "package"
    try:
        return normalize_profile_choice(profile)
    except ValueError:
        return profile


def tool_enabled(root: Path, name: str) -> bool:
    """Return whether a generated project has a named quality tool enabled."""
    config = load_scaffold_guard_toml(root)
    tools = table_value(config, "tools")
    profile = project_profile(root)
    python_default = profile in {"python", "monorepo"}
    if name == "ruff":
        return _ruff_enabled(tools, default=python_default)
    if name in {"mypy", "pyright"}:
        return _python_type_tool_enabled(tools, name=name, default=python_default)
    if name in {"typescript", "typescript_strict", "biome", "vitest"}:
        return bool_value(tools, name, default=profile in {"typescript", "monorepo"})
    return bool_value(tools, name, default=False)


def _ruff_enabled(tools: Mapping[str, object], *, default: bool) -> bool:
    """Return Ruff enablement from mode-aware or legacy tool config."""
    ruff_mode = str_value(tools, "ruff_mode")
    if ruff_mode in {"strict", "standard", "off"}:
        return ruff_mode != "off"
    return bool_value(tools, "ruff", default=default)


def _python_type_tool_enabled(
    tools: Mapping[str, object],
    *,
    name: str,
    default: bool,
) -> bool:
    """Return mypy or Pyright enablement from mode-aware or legacy tool config."""
    typecheck_mode = str_value(tools, "python_typecheck")
    typechecker = str_value(tools, "python_typechecker") or "mypy+pyright"
    if typecheck_mode not in {"strict", "standard", "off"}:
        return bool_value(tools, name, default=default)
    if typecheck_mode == "off":
        return False
    if name == "mypy":
        return typechecker in {"mypy+pyright", "mypy"}
    return typechecker in {"mypy+pyright", "pyright"}


def policy_enabled(root: Path, name: str) -> bool:
    """Return whether a generated project has a named policy rule enabled."""
    config = load_scaffold_guard_toml(root)
    policy = table_value(config, "policy")
    return bool_value(policy, name, default=True)
