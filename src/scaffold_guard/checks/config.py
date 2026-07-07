"""Small TOML and generated-project config helpers."""

import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import cast


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
    """Return whether generated GitHub Actions CI is enabled for a project."""
    config = load_scaffold_guard_toml(root)
    features = table_value(config, "features")
    return bool_value(features, "github_actions", default=True)


def project_profile(root: Path) -> str:
    """Return the generated project profile, defaulting to the original package profile."""
    config = load_scaffold_guard_toml(root)
    project = table_value(config, "project")
    return str_value(project, "profile") or "package"
