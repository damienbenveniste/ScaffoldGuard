"""Shared models for project policy checks."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

FindingSeverity = Literal["error", "warning"]


@dataclass(frozen=True, slots=True)
class CheckFinding:
    """One policy finding from an agent-safe check."""

    path: str
    line: int
    severity: FindingSeverity
    code: str
    message: str

    def to_json(self) -> dict[str, object]:
        """Return a JSON-serializable finding shape."""
        return {
            "path": self.path,
            "line": self.line,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Result for one named policy checker."""

    id: str
    findings: tuple[CheckFinding, ...]

    @property
    def ok(self) -> bool:
        """Return whether this checker has no error findings."""
        return not any(finding.severity == "error" for finding in self.findings)

    def to_json(self) -> dict[str, object]:
        """Return a JSON-serializable check result shape."""
        return {
            "id": self.id,
            "ok": self.ok,
            "findings": [finding.to_json() for finding in self.findings],
        }


@dataclass(frozen=True, slots=True)
class CheckReport:
    """Aggregate project check report."""

    path: Path
    checks: tuple[CheckResult, ...]

    @property
    def ok(self) -> bool:
        """Return whether every checker passed without error findings."""
        return all(check.ok for check in self.checks)

    def to_json(self) -> dict[str, object]:
        """Return a JSON-serializable report shape."""
        return {
            "ok": self.ok,
            "path": str(self.path),
            "checks": [check.to_json() for check in self.checks],
        }


class CheckConfigurationError(ValueError):
    """Raised when checks cannot run because the target path is invalid."""


def finding(
    path: Path | str,
    *,
    line: int,
    code: str,
    message: str,
    severity: FindingSeverity = "error",
) -> CheckFinding:
    """Build a policy finding with normalized path text."""
    path_text = path.as_posix() if isinstance(path, Path) else path
    return CheckFinding(
        path=path_text,
        line=line,
        severity=severity,
        code=code,
        message=message,
    )
