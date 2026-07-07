"""Environment and generated-project diagnostics."""

import asyncio
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path

from scaffold_guard.checks.config import load_toml, project_profile
from scaffold_guard.project_config import ProjectConfigError, load_generated_project_config


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    """One doctor diagnostic result."""

    id: str
    ok: bool
    severity: str
    message: str

    def to_json(self) -> dict[str, object]:
        """Return a JSON-serializable diagnostic check."""
        return {
            "id": self.id,
            "ok": self.ok,
            "severity": self.severity,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class DoctorReport:
    """Aggregate doctor diagnostics."""

    path: Path
    checks: tuple[DoctorCheck, ...]

    @property
    def ok(self) -> bool:
        """Return whether all error-level diagnostics passed."""
        return all(check.ok or check.severity == "warning" for check in self.checks)

    def to_json(self) -> dict[str, object]:
        """Return a JSON-serializable doctor report."""
        return {
            "ok": self.ok,
            "path": str(self.path),
            "checks": [check.to_json() for check in self.checks],
        }


def run_doctor(path: Path) -> DoctorReport:
    """Run environment and generated-project diagnostics."""
    root = path.resolve(strict=False)
    checks = [
        _python_version_check(),
        _executable_check("uv"),
        _executable_check("git"),
        _project_root_check(root),
        _pyproject_parse_check(root),
        *_generated_project_checks(root),
        _git_repository_check(root),
    ]
    return DoctorReport(path=root, checks=tuple(checks))


def _python_version_check() -> DoctorCheck:
    """Report the running Python version."""
    version = platform.python_version()
    return DoctorCheck(
        id="python-version",
        ok=True,
        severity="info",
        message=f"Python {version}",
    )


def _executable_check(name: str) -> DoctorCheck:
    """Report whether an executable is available."""
    path = shutil.which(name)
    return DoctorCheck(
        id=f"{name}-available",
        ok=path is not None,
        severity="error",
        message=f"{name} found at {path}" if path else f"{name} was not found on PATH.",
    )


def _project_root_check(root: Path) -> DoctorCheck:
    """Report whether the target path exists as a directory."""
    return DoctorCheck(
        id="project-root",
        ok=root.exists() and root.is_dir(),
        severity="error",
        message=f"Project root detected: {root}"
        if root.is_dir()
        else f"Project root missing: {root}",
    )


def _pyproject_parse_check(root: Path) -> DoctorCheck:
    """Report whether `pyproject.toml` is present and parseable."""
    pyproject_path = root / "pyproject.toml"
    if not pyproject_path.exists():
        if project_profile(root) == "minimal":
            return DoctorCheck(
                id="pyproject",
                ok=True,
                severity="info",
                message="pyproject.toml is not required for the minimal profile.",
            )
        return DoctorCheck(
            id="pyproject",
            ok=False,
            severity="error",
            message="pyproject.toml is missing.",
        )
    try:
        load_toml(pyproject_path)
    except ValueError as exc:
        return DoctorCheck(
            id="pyproject",
            ok=False,
            severity="error",
            message=f"pyproject.toml is not parseable: {exc}",
        )
    return DoctorCheck(id="pyproject", ok=True, severity="info", message="pyproject.toml parses.")


def _generated_project_checks(root: Path) -> tuple[DoctorCheck, ...]:
    """Report generated-project specific health."""
    try:
        config = load_generated_project_config(root)
    except ProjectConfigError as exc:
        return (
            DoctorCheck(
                id="scaffold-guard-config",
                ok=False,
                severity="error",
                message=str(exc),
            ),
        )

    checks = [
        DoctorCheck(
            id="scaffold-guard-config",
            ok=True,
            severity="info",
            message="scaffold-guard.toml parses.",
        ),
        DoctorCheck(
            id="agents-md",
            ok=(root / "AGENTS.md").exists(),
            severity="error",
            message="AGENTS.md present." if (root / "AGENTS.md").exists() else "AGENTS.md missing.",
        ),
    ]
    if config.profile == "package":
        checks.append(
            DoctorCheck(
                id="package-import-directory",
                ok=(root / "src" / config.package).is_dir(),
                severity="error",
                message=f"Package import directory: src/{config.package}",
            )
        )
    if config.claude:
        checks.append(
            DoctorCheck(
                id="claude-adapter",
                ok=(root / "CLAUDE.md").exists(),
                severity="error",
                message="Claude adapter selected.",
            )
        )
    if config.cursor:
        checks.append(
            DoctorCheck(
                id="cursor-adapter",
                ok=(root / ".cursor/rules").is_dir(),
                severity="error",
                message="Cursor adapter selected.",
            )
        )
    if config.github_actions:
        checks.append(
            DoctorCheck(
                id="github-actions",
                ok=(root / ".github/workflows/ci.yml").exists(),
                severity="error",
                message="GitHub Actions CI configured.",
            )
        )
    return tuple(checks)


def _git_repository_check(root: Path) -> DoctorCheck:
    """Report whether the project is inside a git repository."""
    git_path = shutil.which("git")
    if git_path is None:
        return DoctorCheck(
            id="git-repository",
            ok=False,
            severity="warning",
            message="git unavailable; repository status could not be checked.",
        )
    result = asyncio.run(_run_git(git_path, root))
    return DoctorCheck(
        id="git-repository",
        ok=result,
        severity="warning",
        message="Inside a git repository." if result else "Not inside a git repository.",
    )


async def _run_git(git_path: str, root: Path) -> bool:
    """Run git repository detection asynchronously."""
    process = await asyncio.create_subprocess_exec(
        git_path,
        "rev-parse",
        "--is-inside-work-tree",
        cwd=root,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _stderr = await process.communicate()
    return process.returncode == 0 and stdout.decode("utf-8", errors="replace").strip() == "true"
