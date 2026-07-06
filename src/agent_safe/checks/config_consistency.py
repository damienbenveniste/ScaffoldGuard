"""Checks that generated config matches generated files."""

import re
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from agent_safe.checks.base import CheckFinding, CheckResult, finding
from agent_safe.checks.config import (
    bool_value,
    int_value,
    load_agent_safe_toml,
    str_value,
    table_value,
)

REQUIRES_PYTHON = re.compile(r"requires-python\s*=\s*[\"']>=([^\"']+)[\"']")
PYPROJECT_COVERAGE = re.compile(r"fail_under\s*=\s*(\d+)")


def check_config_consistency(root: Path) -> CheckResult:
    """Verify generated config values match generated files."""
    findings: list[CheckFinding] = []
    config_path = root / "agent-safe.toml"
    pyproject_path = root / "pyproject.toml"
    if not config_path.exists():
        findings.append(
            finding(
                "agent-safe.toml",
                line=0,
                code="missing-agent-safe-config",
                message="Generated projects must include agent-safe.toml.",
            )
        )
        return CheckResult(id="config-consistency", findings=tuple(findings))

    config = load_agent_safe_toml(root)
    agents = table_value(config, "agents")
    project = table_value(config, "project")

    findings.extend(_check_agent_file_consistency(root, agents))
    if pyproject_path.exists():
        pyproject_text = pyproject_path.read_text(encoding="utf-8", errors="replace")
        findings.extend(_check_coverage(project, pyproject_text))
        findings.extend(_check_python_min(project, pyproject_text))
        findings.extend(_check_lockfile_mtime(root))
    return CheckResult(id="config-consistency", findings=tuple(findings))


def _check_agent_file_consistency(
    root: Path,
    agents: object,
) -> list[CheckFinding]:
    """Verify selected agent booleans match generated adapter files."""
    findings: list[CheckFinding] = []
    agent_table = _object_mapping(agents)
    if bool_value(agent_table, "codex", default=True) and not (root / "AGENTS.md").exists():
        findings.append(
            finding(
                "AGENTS.md",
                line=0,
                code="agent-config-mismatch",
                message="agent-safe.toml enables Codex but AGENTS.md is missing.",
            )
        )
    if bool_value(agent_table, "claude", default=False) != (root / "CLAUDE.md").exists():
        findings.append(
            finding(
                "CLAUDE.md",
                line=0,
                code="agent-config-mismatch",
                message="agent-safe.toml Claude setting does not match CLAUDE.md.",
            )
        )
    if bool_value(agent_table, "cursor", default=False) != (root / ".cursor/rules").exists():
        findings.append(
            finding(
                ".cursor/rules",
                line=0,
                code="agent-config-mismatch",
                message="agent-safe.toml Cursor setting does not match .cursor/rules.",
            )
        )
    return findings


def _check_coverage(project: object, pyproject_text: str) -> list[CheckFinding]:
    """Verify coverage config matches `agent-safe.toml`."""
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
            message="coverage_fail_under in agent-safe.toml must match pyproject.toml.",
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
            message="python_min in agent-safe.toml must match pyproject.toml.",
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
