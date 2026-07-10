"""Typed data models shared across the CLI implementation."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias, cast

AgentChoice: TypeAlias = Literal["codex", "claude", "cursor", "all"]
AdapterSelection: TypeAlias = Literal["codex", "claude", "cursor"]
CanonicalProfileChoice: TypeAlias = Literal["minimal", "python", "typescript", "monorepo"]
ProfileChoice: TypeAlias = Literal["minimal", "python", "package", "typescript", "monorepo"]
LicenseChoice: TypeAlias = Literal["MIT", "Apache-2.0", "none"]
CiChoice: TypeAlias = Literal["github", "gitlab"]
PythonQualityMode: TypeAlias = Literal["strict", "standard", "off"]
PythonTypechecker: TypeAlias = Literal["mypy+pyright", "mypy", "pyright"]
TemplateLifecycle: TypeAlias = Literal["managed", "structured", "seed"]

CANONICAL_PROFILES: frozenset[CanonicalProfileChoice] = frozenset(
    ("minimal", "python", "typescript", "monorepo")
)
SUPPORTED_PROFILES: frozenset[ProfileChoice] = frozenset(
    ("minimal", "python", "package", "typescript", "monorepo")
)
LEGACY_PROFILE_ALIASES: Mapping[str, CanonicalProfileChoice] = {"package": "python"}
AGENT_CHOICE_ADAPTERS: Mapping[AgentChoice, tuple[AdapterSelection, ...]] = {
    "codex": ("codex",),
    "claude": ("claude",),
    "cursor": ("cursor",),
    "all": ("codex", "claude", "cursor"),
}
ADAPTER_ORDER: tuple[AdapterSelection, ...] = ("codex", "claude", "cursor")
AGENT_SELECTION_SENTINEL: tuple[AdapterSelection, ...] = cast(
    "tuple[AdapterSelection, ...]",
    ("__agent__",),
)


def normalize_profile_choice(profile: str) -> CanonicalProfileChoice:
    """Return the canonical profile value, accepting legacy aliases."""
    normalized = profile.strip().lower()
    alias = LEGACY_PROFILE_ALIASES.get(normalized)
    if alias is not None:
        return alias
    if normalized in CANONICAL_PROFILES:
        return normalized
    msg = f"Unsupported project profile: {profile}"
    raise ValueError(msg)


def profile_includes_python(profile: str) -> bool:
    """Return whether a profile includes Python package code."""
    return normalize_profile_choice(profile) in {"python", "monorepo"}


def profile_includes_typescript(profile: str) -> bool:
    """Return whether a profile includes TypeScript package code."""
    return normalize_profile_choice(profile) in {"typescript", "monorepo"}


def adapter_selection_for_agent(agent: AgentChoice) -> tuple[AdapterSelection, ...]:
    """Return exact adapter selections for a CLI shorthand value."""
    return AGENT_CHOICE_ADAPTERS[agent]


def normalize_adapter_selection(
    selection: tuple[AdapterSelection, ...],
) -> tuple[AdapterSelection, ...]:
    """Return a deterministic, validated exact adapter selection."""
    unknown = tuple(adapter for adapter in selection if adapter not in ADAPTER_ORDER)
    if unknown:
        msg = f"Unsupported agent adapter: {unknown[0]}"
        raise ValueError(msg)
    if len(set(selection)) != len(selection):
        msg = "Agent adapter selections must be unique."
        raise ValueError(msg)
    return tuple(adapter for adapter in ADAPTER_ORDER if adapter in selection)


@dataclass(frozen=True, slots=True)
class TemplateSpec:
    """A packaged template and its generated destination path."""

    template_id: str
    template_name: str
    destination: str
    lifecycle: TemplateLifecycle


@dataclass(frozen=True, slots=True)
class InitOptions:
    """Validated options for generating a starter project."""

    target_dir: Path
    project_slug: str
    package_name: str
    agent: AgentChoice
    profile: ProfileChoice
    license: LicenseChoice
    python_min: str
    coverage: int
    ci: CiChoice
    docs_enabled: bool
    dry_run: bool
    force: bool
    ruff_enabled: bool = True
    mypy_enabled: bool = True
    pyright_enabled: bool = True
    ruff_mode: PythonQualityMode = "strict"
    python_typecheck_mode: PythonQualityMode = "strict"
    python_typechecker: PythonTypechecker = "mypy+pyright"
    typescript_strict_enabled: bool = True
    biome_enabled: bool = True
    vitest_enabled: bool = True
    adapter_selection: tuple[AdapterSelection, ...] = AGENT_SELECTION_SENTINEL

    def __post_init__(self) -> None:
        """Normalize exact adapter selections while preserving CLI shorthand compatibility."""
        selection = (
            adapter_selection_for_agent(self.agent)
            if self.adapter_selection == AGENT_SELECTION_SENTINEL
            else self.adapter_selection
        )
        object.__setattr__(self, "adapter_selection", normalize_adapter_selection(selection))

    @property
    def python_enabled(self) -> bool:
        """Return whether the generated profile includes Python package code."""
        return profile_includes_python(self.profile)

    @property
    def typescript_enabled(self) -> bool:
        """Return whether the generated profile includes TypeScript package code."""
        return profile_includes_typescript(self.profile)

    @property
    def codex_enabled(self) -> bool:
        """Return whether Codex-oriented files should be generated."""
        return "codex" in self.adapter_selection

    @property
    def claude_enabled(self) -> bool:
        """Return whether Claude Code adapter files should be generated."""
        return "claude" in self.adapter_selection

    @property
    def cursor_enabled(self) -> bool:
        """Return whether Cursor adapter files should be generated."""
        return "cursor" in self.adapter_selection


@dataclass(frozen=True, slots=True)
class ScaffoldSummary:
    """Summary of planned or written scaffold files."""

    target_dir: Path
    files: tuple[Path, ...]
    dry_run: bool
