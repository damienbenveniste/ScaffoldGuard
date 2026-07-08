"""Typed data models shared across the CLI implementation."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias

AgentChoice: TypeAlias = Literal["codex", "claude", "cursor", "all"]
CanonicalProfileChoice: TypeAlias = Literal["minimal", "python", "typescript", "monorepo"]
ProfileChoice: TypeAlias = Literal["minimal", "python", "package", "typescript", "monorepo"]
LicenseChoice: TypeAlias = Literal["MIT", "Apache-2.0", "none"]
CiChoice: TypeAlias = Literal["github", "gitlab"]
PythonQualityMode: TypeAlias = Literal["strict", "standard", "off"]
PythonTypechecker: TypeAlias = Literal["mypy+pyright", "mypy", "pyright"]

CANONICAL_PROFILES: frozenset[CanonicalProfileChoice] = frozenset(
    ("minimal", "python", "typescript", "monorepo")
)
SUPPORTED_PROFILES: frozenset[ProfileChoice] = frozenset(
    ("minimal", "python", "package", "typescript", "monorepo")
)
LEGACY_PROFILE_ALIASES: Mapping[str, CanonicalProfileChoice] = {"package": "python"}


def normalize_profile_choice(profile: str) -> ProfileChoice:
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


@dataclass(frozen=True, slots=True)
class TemplateSpec:
    """A packaged template and its generated destination path."""

    template_name: str
    destination: str


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
        return self.agent in {"codex", "all"}

    @property
    def claude_enabled(self) -> bool:
        """Return whether Claude Code adapter files should be generated."""
        return self.agent in {"claude", "all"}

    @property
    def cursor_enabled(self) -> bool:
        """Return whether Cursor adapter files should be generated."""
        return self.agent in {"cursor", "all"}


@dataclass(frozen=True, slots=True)
class ScaffoldSummary:
    """Summary of planned or written scaffold files."""

    target_dir: Path
    files: tuple[Path, ...]
    dry_run: bool
