"""Typed data models shared across the CLI implementation."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias

AgentChoice: TypeAlias = Literal["codex", "claude", "cursor", "all"]
ProfileChoice: TypeAlias = Literal["minimal", "package"]
LicenseChoice: TypeAlias = Literal["MIT", "Apache-2.0", "none"]


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
    ci: str
    docs_enabled: bool
    dry_run: bool
    force: bool

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
