"""Generated project configuration loading."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from scaffold_guard.checks.config import (
    bool_value,
    int_value,
    load_scaffold_guard_toml,
    str_value,
    table_value,
)
from scaffold_guard.models import AgentChoice, InitOptions, ProfileChoice

SUPPORTED_PROFILES: tuple[ProfileChoice, ...] = ("minimal", "package")


class ProjectConfigError(ValueError):
    """Raised when a generated project configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class GeneratedProjectConfig:
    """Parsed subset of `scaffold-guard.toml` used by V1 commands."""

    root: Path
    name: str
    package: str
    profile: ProfileChoice
    python_min: str
    coverage_fail_under: int
    codex: bool
    claude: bool
    cursor: bool
    docs: bool
    github_actions: bool

    @property
    def agent_choice(self) -> AgentChoice:
        """Return the closest CLI agent selection represented by enabled flags."""
        if self.claude and self.cursor:
            return "all"
        if self.claude:
            return "claude"
        if self.cursor:
            return "cursor"
        return "codex"

    def to_init_options(self, *, dry_run: bool, force: bool) -> InitOptions:
        """Convert config into scaffold options for rule regeneration."""
        return InitOptions(
            target_dir=self.root,
            project_slug=self.name,
            package_name=self.package,
            agent=self.agent_choice,
            profile=self.profile,
            license="MIT",
            python_min=self.python_min,
            coverage=self.coverage_fail_under,
            ci="github",
            docs_enabled=self.docs,
            dry_run=dry_run,
            force=force,
        )

    def to_json(self) -> dict[str, object]:
        """Return JSON-serializable project config fields."""
        return {
            "name": self.name,
            "package": self.package,
            "profile": self.profile,
            "python_min": self.python_min,
            "coverage_fail_under": self.coverage_fail_under,
            "agents": {
                "codex": self.codex,
                "claude": self.claude,
                "cursor": self.cursor,
            },
            "features": {
                "docs": self.docs,
                "github_actions": self.github_actions,
            },
        }


def load_generated_project_config(root: Path) -> GeneratedProjectConfig:
    """Load and validate required `scaffold-guard.toml` fields."""
    resolved_root = root.resolve(strict=False)
    config_path = resolved_root / "scaffold-guard.toml"
    if not config_path.exists():
        msg = f"Generated project config is missing: {config_path}"
        raise ProjectConfigError(msg)

    config = load_scaffold_guard_toml(resolved_root)
    project = table_value(config, "project")
    agents = table_value(config, "agents")
    features = table_value(config, "features")

    name = _required_str(project, "name")
    package = _required_str(project, "package")
    profile = _required_profile(project, "profile")
    python_min = _required_str(project, "python_min")
    coverage = _required_int(project, "coverage_fail_under")
    return GeneratedProjectConfig(
        root=resolved_root,
        name=name,
        package=package,
        profile=profile,
        python_min=python_min,
        coverage_fail_under=coverage,
        codex=bool_value(agents, "codex", default=True),
        claude=bool_value(agents, "claude", default=False),
        cursor=bool_value(agents, "cursor", default=False),
        docs=bool_value(features, "docs", default=True),
        github_actions=bool_value(features, "github_actions", default=True),
    )


def _required_str(table: Mapping[str, object], key: str) -> str:
    """Return a required string field from a TOML table."""
    value = str_value(table, key)
    if value is None:
        msg = f"Missing required string config value: {key}"
        raise ProjectConfigError(msg)
    return value


def _required_profile(table: Mapping[str, object], key: str) -> ProfileChoice:
    """Return a required supported profile field from a TOML table."""
    value = _required_str(table, key)
    if value in SUPPORTED_PROFILES:
        return value
    msg = f"Unsupported generated project profile: {value}"
    raise ProjectConfigError(msg)


def _required_int(table: Mapping[str, object], key: str) -> int:
    """Return a required integer field from a TOML table."""
    value = int_value(table, key)
    if value is None:
        msg = f"Missing required integer config value: {key}"
        raise ProjectConfigError(msg)
    return value
