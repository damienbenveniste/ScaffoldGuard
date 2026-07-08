"""Generated project configuration loading."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from scaffold_guard.checks.config import (
    bool_value,
    int_value,
    load_scaffold_guard_toml,
    str_value,
    table_value,
)
from scaffold_guard.models import (
    SUPPORTED_PROFILES,
    AgentChoice,
    CiChoice,
    InitOptions,
    ProfileChoice,
    PythonQualityMode,
    PythonTypechecker,
    normalize_profile_choice,
    profile_includes_python,
    profile_includes_typescript,
)

SUPPORTED_CI: tuple[CiChoice, ...] = ("github", "gitlab")


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
    ci: CiChoice
    codex: bool
    claude: bool
    cursor: bool
    docs: bool
    github_actions: bool
    gitlab_ci: bool
    ruff: bool
    mypy: bool
    pyright: bool
    ruff_mode: PythonQualityMode
    python_typecheck_mode: PythonQualityMode
    python_typechecker: PythonTypechecker
    typescript_strict: bool
    biome: bool
    vitest: bool

    @property
    def python(self) -> bool:
        """Return whether the generated project includes Python package code."""
        return profile_includes_python(self.profile)

    @property
    def typescript(self) -> bool:
        """Return whether the generated project includes TypeScript package code."""
        return profile_includes_typescript(self.profile)

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
            ci=self.ci,
            docs_enabled=self.docs,
            dry_run=dry_run,
            force=force,
            ruff_enabled=self.ruff,
            mypy_enabled=self.mypy,
            pyright_enabled=self.pyright,
            ruff_mode=self.ruff_mode,
            python_typecheck_mode=self.python_typecheck_mode,
            python_typechecker=self.python_typechecker,
            typescript_strict_enabled=self.typescript_strict,
            biome_enabled=self.biome,
            vitest_enabled=self.vitest,
        )

    def to_json(self) -> dict[str, object]:
        """Return JSON-serializable project config fields."""
        tools: dict[str, object] = {
            "ruff": self.ruff,
            "ruff_mode": self.ruff_mode,
            "mypy": self.mypy,
            "pyright": self.pyright,
            "python_typecheck": self.python_typecheck_mode,
            "python_typechecker": self.python_typechecker,
        }
        if self.typescript:
            tools.update(
                {
                    "typescript": True,
                    "typescript_strict": self.typescript_strict,
                    "biome": self.biome,
                    "vitest": self.vitest,
                }
            )
        return {
            "name": self.name,
            "package": self.package,
            "profile": self.profile,
            "python_min": self.python_min,
            "coverage_fail_under": self.coverage_fail_under,
            "ci": self.ci,
            "agents": {
                "codex": self.codex,
                "claude": self.claude,
                "cursor": self.cursor,
            },
            "features": {
                "docs": self.docs,
                "github_actions": self.github_actions,
                "gitlab_ci": self.gitlab_ci,
            },
            "tools": tools,
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
    tools = table_value(config, "tools")

    name = _required_str(project, "name")
    package = _required_str(project, "package")
    profile = _required_profile(project, "profile")
    python_tool_default = profile_includes_python(profile)
    typescript_tool_default = profile_includes_typescript(profile)
    ruff_mode = _optional_quality_mode(tools, "ruff_mode")
    if ruff_mode is None:
        ruff = bool_value(tools, "ruff", default=python_tool_default)
        ruff_mode = "strict" if ruff else "off"
    else:
        ruff = ruff_mode != "off"
    python_typecheck_mode = _optional_quality_mode(tools, "python_typecheck")
    if python_typecheck_mode is None:
        mypy = bool_value(tools, "mypy", default=python_tool_default)
        pyright = bool_value(tools, "pyright", default=python_tool_default)
        python_typecheck_mode = "strict" if (mypy or pyright) else "off"
        python_typechecker = _typechecker_from_booleans(mypy=mypy, pyright=pyright)
    else:
        python_typechecker = _optional_typechecker(tools, "python_typechecker") or "mypy+pyright"
        mypy, pyright = _typechecker_enabled(python_typecheck_mode, python_typechecker)
    ci = _optional_ci(project, features)
    python_min = _required_str(project, "python_min")
    coverage = _required_int(project, "coverage_fail_under")
    return GeneratedProjectConfig(
        root=resolved_root,
        name=name,
        package=package,
        profile=profile,
        python_min=python_min,
        coverage_fail_under=coverage,
        ci=ci,
        codex=bool_value(agents, "codex", default=True),
        claude=bool_value(agents, "claude", default=False),
        cursor=bool_value(agents, "cursor", default=False),
        docs=bool_value(features, "docs", default=True),
        github_actions=bool_value(features, "github_actions", default=ci == "github"),
        gitlab_ci=bool_value(features, "gitlab_ci", default=ci == "gitlab"),
        ruff=ruff,
        mypy=mypy,
        pyright=pyright,
        ruff_mode=ruff_mode,
        python_typecheck_mode=python_typecheck_mode,
        python_typechecker=python_typechecker,
        typescript_strict=bool_value(
            tools,
            "typescript_strict",
            default=typescript_tool_default,
        ),
        biome=bool_value(tools, "biome", default=typescript_tool_default),
        vitest=bool_value(tools, "vitest", default=typescript_tool_default),
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
        return normalize_profile_choice(value)
    msg = f"Unsupported generated project profile: {value}"
    raise ProjectConfigError(msg)


def _optional_ci(project: Mapping[str, object], features: Mapping[str, object]) -> CiChoice:
    """Return configured CI provider, defaulting old configs to GitHub Actions."""
    value = str_value(project, "ci")
    if value in SUPPORTED_CI:
        return value
    if value is not None:
        msg = f"Unsupported generated project CI provider: {value}"
        raise ProjectConfigError(msg)
    if bool_value(features, "gitlab_ci", default=False):
        return "gitlab"
    return "github"


def _optional_quality_mode(table: Mapping[str, object], key: str) -> PythonQualityMode | None:
    """Return an optional Python quality strictness mode."""
    value = str_value(table, key)
    if value in {"strict", "standard", "off"}:
        return cast("PythonQualityMode", value)
    return None


def _optional_typechecker(table: Mapping[str, object], key: str) -> PythonTypechecker | None:
    """Return an optional Python type checker selection."""
    value = str_value(table, key)
    if value in {"mypy+pyright", "mypy", "pyright"}:
        return cast("PythonTypechecker", value)
    return None


def _typechecker_enabled(
    mode: PythonQualityMode,
    checker: PythonTypechecker,
) -> tuple[bool, bool]:
    """Return mypy and Pyright enablement for a type-checking mode and checker."""
    if mode == "off":
        return False, False
    return checker in {"mypy+pyright", "mypy"}, checker in {"mypy+pyright", "pyright"}


def _typechecker_from_booleans(*, mypy: bool, pyright: bool) -> PythonTypechecker:
    """Return the closest checker selection represented by legacy booleans."""
    if mypy and not pyright:
        return "mypy"
    if pyright and not mypy:
        return "pyright"
    return "mypy+pyright"


def _required_int(table: Mapping[str, object], key: str) -> int:
    """Return a required integer field from a TOML table."""
    value = int_value(table, key)
    if value is None:
        msg = f"Missing required integer config value: {key}"
        raise ProjectConfigError(msg)
    return value
