"""Typed data models shared across the CLI implementation."""

from __future__ import annotations

import re
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
MonorepoLayoutChoice: TypeAlias = Literal["application", "library", "custom"]
MonorepoLayout: TypeAlias = Literal["application", "library", "custom", "legacy"]

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
MONOREPO_LAYOUTS: frozenset[MonorepoLayoutChoice] = frozenset(("application", "library", "custom"))
PERSISTED_MONOREPO_LAYOUTS: frozenset[MonorepoLayout] = frozenset((*MONOREPO_LAYOUTS, "legacy"))
RESERVED_WORKSPACE_ROOTS: frozenset[str] = frozenset(
    (".git", ".github", ".scaffold-guard", ".codex", ".claude", ".cursor")
)
WORKSPACE_PATH_SEGMENT: re.Pattern[str] = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
AGENT_SELECTION_SENTINEL: tuple[AdapterSelection, ...] = cast(
    "tuple[AdapterSelection, ...]",
    ("__agent__",),
)


@dataclass(frozen=True, slots=True)
class WorkspacePath:
    """A validated relative directory path for one monorepo workspace."""

    path: Path

    def __post_init__(self) -> None:
        """Reject unsafe, ambiguous, and control-root workspace paths."""
        raw_path = self.path.as_posix()
        if raw_path in {"", "."} or self.path == Path():
            raise ValueError("Workspace path must not be empty or '.'.")
        if self.path.is_absolute():
            msg = f"Workspace path must be relative: {raw_path}"
            raise ValueError(msg)
        if ".." in self.path.parts:
            msg = f"Workspace path must not contain '..': {raw_path}"
            raise ValueError(msg)
        if self.path.parts[0] in RESERVED_WORKSPACE_ROOTS:
            msg = f"Workspace path must not use reserved control root: {self.path.parts[0]}"
            raise ValueError(msg)
        invalid_segment = next(
            (part for part in self.path.parts if WORKSPACE_PATH_SEGMENT.fullmatch(part) is None),
            None,
        )
        if invalid_segment is not None:
            msg = (
                "Workspace path segments must start with an ASCII letter or digit and "
                f"contain only letters, digits, '.', '_', or '-': {invalid_segment}"
            )
            raise ValueError(msg)

    @classmethod
    def parse(cls, value: str, *, field_name: str) -> WorkspacePath:
        """Parse a nonempty POSIX-style relative workspace directory path."""
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{field_name} must not be empty.")
        if "\\" in stripped:
            raise ValueError(f"{field_name} must use '/' as the path separator.")
        if any(part == "." for part in stripped.split("/")):
            raise ValueError(f"{field_name} must not contain '.'.")
        try:
            return cls(Path(stripped))
        except ValueError as exc:
            raise ValueError(f"Invalid {field_name}: {exc}") from exc

    def as_posix(self) -> str:
        """Return the normalized relative workspace path."""
        return self.path.as_posix()


@dataclass(frozen=True, slots=True)
class MonorepoWorkspaces:
    """A validated monorepo layout and its exact language workspace paths."""

    layout: MonorepoLayout
    python: WorkspacePath
    typescript: WorkspacePath

    def __post_init__(self) -> None:
        """Reject overlapping workspaces and paths inconsistent with fixed layouts."""
        if self.python.path == self.typescript.path:
            raise ValueError("Python and TypeScript workspace paths must be different.")
        if self.python.path.is_relative_to(
            self.typescript.path
        ) or self.typescript.path.is_relative_to(self.python.path):
            raise ValueError("Python and TypeScript workspace paths must not overlap.")
        expected = fixed_monorepo_workspace_paths(self.layout)
        if expected is not None and (self.python, self.typescript) != expected:
            raise ValueError(
                f"{self.layout} monorepo layout requires workspaces "
                f"{expected[0].as_posix()} and {expected[1].as_posix()}."
            )


def fixed_monorepo_workspace_paths(
    layout: MonorepoLayout,
) -> tuple[WorkspacePath, WorkspacePath] | None:
    """Return fixed workspace paths for a predefined or legacy layout."""
    if layout == "application":
        return WorkspacePath(Path("apps/api")), WorkspacePath(Path("apps/web"))
    if layout == "library":
        return WorkspacePath(Path("packages/core")), WorkspacePath(Path("packages/client"))
    if layout == "legacy":
        return WorkspacePath(Path("packages/python")), WorkspacePath(Path("packages/typescript"))
    return None


def monorepo_workspaces(
    layout: MonorepoLayout,
    *,
    python_workspace: WorkspacePath | None = None,
    typescript_workspace: WorkspacePath | None = None,
) -> MonorepoWorkspaces:
    """Build validated workspace state for a monorepo layout."""
    fixed_paths = fixed_monorepo_workspace_paths(layout)
    if fixed_paths is not None:
        python_path, typescript_path = fixed_paths
        if python_workspace is not None:
            python_path = python_workspace
        if typescript_workspace is not None:
            typescript_path = typescript_workspace
        return MonorepoWorkspaces(layout, python_path, typescript_path)
    if layout != "custom":
        msg = f"Unsupported monorepo layout: {layout}"
        raise ValueError(msg)
    if python_workspace is None or typescript_workspace is None:
        raise ValueError("Custom monorepo layout requires both workspace paths.")
    return MonorepoWorkspaces(layout, python_workspace, typescript_workspace)


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
    monorepo_layout: MonorepoLayout | None = None
    python_workspace: WorkspacePath | None = None
    typescript_workspace: WorkspacePath | None = None

    def __post_init__(self) -> None:
        """Normalize adapter and monorepo selections while preserving compatibility."""
        selection = (
            adapter_selection_for_agent(self.agent)
            if self.adapter_selection == AGENT_SELECTION_SENTINEL
            else self.adapter_selection
        )
        object.__setattr__(self, "adapter_selection", normalize_adapter_selection(selection))
        if normalize_profile_choice(self.profile) != "monorepo":
            if (
                self.monorepo_layout is not None
                or self.python_workspace is not None
                or self.typescript_workspace is not None
            ):
                raise ValueError("Monorepo layout options require the monorepo profile.")
            return
        workspaces = monorepo_workspaces(
            self.monorepo_layout or "application",
            python_workspace=self.python_workspace,
            typescript_workspace=self.typescript_workspace,
        )
        object.__setattr__(self, "monorepo_layout", workspaces.layout)
        object.__setattr__(self, "python_workspace", workspaces.python)
        object.__setattr__(self, "typescript_workspace", workspaces.typescript)

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
