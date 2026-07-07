"""Typed data models shared across the CLI implementation."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias

AgentChoice: TypeAlias = Literal["codex", "claude", "cursor", "all"]
ProfileChoice: TypeAlias = Literal["minimal", "package"]
LicenseChoice: TypeAlias = Literal["MIT", "Apache-2.0", "none"]
CiChoice: TypeAlias = Literal["github", "gitlab"]
RuffPresetChoice: TypeAlias = Literal["strict", "standard", "minimal", "off"]
MypyPresetChoice: TypeAlias = Literal["strict", "standard", "off"]
PyrightPresetChoice: TypeAlias = Literal["strict", "basic", "off"]

RUFF_PRESETS: tuple[RuffPresetChoice, ...] = ("strict", "standard", "minimal", "off")
MYPY_PRESETS: tuple[MypyPresetChoice, ...] = ("strict", "standard", "off")
PYRIGHT_PRESETS: tuple[PyrightPresetChoice, ...] = ("strict", "basic", "off")


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
    ruff_preset: RuffPresetChoice = "strict"
    mypy_preset: MypyPresetChoice = "strict"
    pyright_preset: PyrightPresetChoice = "strict"

    @property
    def ruff_enabled(self) -> bool:
        """Return whether Ruff should be configured in the generated package."""
        return self.ruff_preset != "off"

    @property
    def mypy_enabled(self) -> bool:
        """Return whether mypy should be configured in the generated package."""
        return self.mypy_preset != "off"

    @property
    def pyright_enabled(self) -> bool:
        """Return whether Pyright should be configured in the generated package."""
        return self.pyright_preset != "off"

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
