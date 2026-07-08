"""Checks that generated config matches generated files."""

import re
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from scaffold_guard.checks.base import CheckFinding, CheckResult, finding
from scaffold_guard.checks.config import (
    bool_value,
    int_value,
    load_scaffold_guard_toml,
    str_value,
    table_value,
)

REQUIRES_PYTHON: re.Pattern[str] = re.compile(r"requires-python\s*=\s*[\"']>=([^\"']+)[\"']")
PYPROJECT_COVERAGE: re.Pattern[str] = re.compile(r"fail_under\s*=\s*(\d+)")
VITEST_COVERAGE: re.Pattern[str] = re.compile(r"(?:branches|functions|lines|statements):\s*(\d+)")
CODEX_ADAPTER_PATHS: tuple[Path, ...] = (
    Path("AGENTS.md"),
    Path(".codex/config.toml"),
    Path(".codex/hooks.json"),
    Path(".codex/agents/implementation-worker.toml"),
    Path(".codex/agents/docs-worker.toml"),
    Path(".codex/agents/reviewer.toml"),
    Path(".codex/hooks/workflow-evidence.sh"),
    Path(".codex/rules/git.rules"),
    Path(".codex/rules/validation.rules"),
)


def check_config_consistency(root: Path) -> CheckResult:
    """Verify generated config values match generated files."""
    findings: list[CheckFinding] = []
    config_path = root / "scaffold-guard.toml"
    pyproject_path = root / "pyproject.toml"
    if not config_path.exists():
        findings.append(
            finding(
                "scaffold-guard.toml",
                line=0,
                code="missing-scaffold-guard-config",
                message="Generated projects must include scaffold-guard.toml.",
            )
        )
        return CheckResult(id="config-consistency", findings=tuple(findings))

    config = load_scaffold_guard_toml(root)
    agents = table_value(config, "agents")
    project = table_value(config, "project")

    findings.extend(_check_agent_file_consistency(root, agents))
    if pyproject_path.exists():
        pyproject_text = pyproject_path.read_text(encoding="utf-8", errors="replace")
        findings.extend(_check_coverage(project, pyproject_text))
        findings.extend(_check_python_min(project, pyproject_text))
        findings.extend(_check_lockfile_mtime(root))
    for relative_path in (Path("vitest.config.ts"), Path("packages/typescript/vitest.config.ts")):
        vitest_path = root / relative_path
        if vitest_path.exists():
            vitest_text = vitest_path.read_text(encoding="utf-8", errors="replace")
            findings.extend(_check_typescript_coverage(project, relative_path, vitest_text))
    return CheckResult(id="config-consistency", findings=tuple(findings))


def _check_agent_file_consistency(
    root: Path,
    agents: object,
) -> list[CheckFinding]:
    """Verify selected agent booleans match generated adapter files."""
    findings: list[CheckFinding] = []
    agent_table = _object_mapping(agents)
    codex_enabled = bool_value(agent_table, "codex", default=True)
    findings.extend(_check_codex_file_consistency(root, codex_enabled))
    if bool_value(agent_table, "claude", default=False) != (root / "CLAUDE.md").exists():
        findings.append(
            finding(
                "CLAUDE.md",
                line=0,
                code="agent-config-mismatch",
                message="scaffold-guard.toml Claude setting does not match CLAUDE.md.",
            )
        )
    if bool_value(agent_table, "cursor", default=False) != (root / ".cursor/rules").exists():
        findings.append(
            finding(
                ".cursor/rules",
                line=0,
                code="agent-config-mismatch",
                message="scaffold-guard.toml Cursor setting does not match .cursor/rules.",
            )
        )
    return findings


def _check_codex_file_consistency(root: Path, codex_enabled: bool) -> list[CheckFinding]:
    """Verify Codex adapter files match the generated config flag."""
    findings: list[CheckFinding] = []
    missing_paths = tuple(path for path in CODEX_ADAPTER_PATHS if not (root / path).exists())
    if codex_enabled:
        findings.extend(
            finding(
                relative_path,
                line=0,
                code="agent-config-mismatch",
                message=f"scaffold-guard.toml enables Codex but {relative_path} is missing.",
            )
            for relative_path in missing_paths
        )
        return findings
    if any((root / path).exists() for path in CODEX_ADAPTER_PATHS if path != Path("AGENTS.md")):
        findings.append(
            finding(
                ".codex",
                line=0,
                code="agent-config-mismatch",
                message="scaffold-guard.toml disables Codex but .codex adapter files exist.",
            )
        )
    return findings


def _check_coverage(project: object, pyproject_text: str) -> list[CheckFinding]:
    """Verify coverage config matches `scaffold-guard.toml`."""
    project_table = _object_mapping(project)
    configured_coverage = int_value(project_table, "coverage_fail_under")
    pyproject_match = PYPROJECT_COVERAGE.search(pyproject_text)
    if configured_coverage is None or pyproject_match is None:
        return []
    pyproject_coverage = int(pyproject_match.group(1))
    if configured_coverage == pyproject_coverage:
        return []
    return [
        finding(
            "pyproject.toml",
            line=1,
            code="coverage-config-mismatch",
            message="coverage_fail_under in scaffold-guard.toml must match pyproject.toml.",
        )
    ]


def _check_python_min(project: object, pyproject_text: str) -> list[CheckFinding]:
    """Verify generated Python minimum version matches `pyproject.toml`."""
    project_table = _object_mapping(project)
    configured_python = str_value(project_table, "python_min")
    pyproject_match = REQUIRES_PYTHON.search(pyproject_text)
    if configured_python is None or pyproject_match is None:
        return []
    pyproject_python = pyproject_match.group(1)
    if configured_python == pyproject_python:
        return []
    return [
        finding(
            "pyproject.toml",
            line=1,
            code="python-min-config-mismatch",
            message="python_min in scaffold-guard.toml must match pyproject.toml.",
        )
    ]


def _check_typescript_coverage(
    project: object,
    relative_path: Path,
    vitest_text: str,
) -> list[CheckFinding]:
    """Verify Vitest coverage thresholds match `scaffold-guard.toml`."""
    project_table = _object_mapping(project)
    configured_coverage = int_value(project_table, "coverage_fail_under")
    vitest_values = {int(match.group(1)) for match in VITEST_COVERAGE.finditer(vitest_text)}
    if configured_coverage is None or not vitest_values or vitest_values == {configured_coverage}:
        return []
    return [
        finding(
            relative_path,
            line=1,
            code="coverage-config-mismatch",
            message="coverage_fail_under in scaffold-guard.toml must match Vitest thresholds.",
        )
    ]


def _check_lockfile_mtime(root: Path) -> list[CheckFinding]:
    """Warn when an existing lockfile appears older than dependency config."""
    pyproject_path = root / "pyproject.toml"
    lockfile_path = root / "uv.lock"
    if not lockfile_path.exists() or not pyproject_path.exists():
        return []
    if lockfile_path.stat().st_mtime >= pyproject_path.stat().st_mtime:
        return []
    return [
        finding(
            "uv.lock",
            line=0,
            severity="warning",
            code="lockfile-older-than-pyproject",
            message="uv.lock is older than pyproject.toml; run uv lock or uv sync.",
        )
    ]


def _object_mapping(value: object) -> Mapping[str, object]:
    """Return a typed object mapping when `value` is mapping-like."""
    if isinstance(value, Mapping):
        return cast("Mapping[str, object]", value)
    return {}
