"""Checks that generated config matches generated files."""

import importlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol, cast

from scaffold_guard.checks.base import CheckFinding, CheckResult, finding
from scaffold_guard.checks.config import (
    bool_value,
    int_value,
    load_scaffold_guard_toml,
    load_toml,
    str_value,
    table_value,
)
from scaffold_guard.models import ProfileChoice, WorkspacePath

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


class _GeneratedProjectConfig(Protocol):
    """Generated config fields needed for workspace consistency checks."""

    package: str
    profile: ProfileChoice
    pyright: bool
    biome: bool
    python_workspace: WorkspacePath | None
    typescript_workspace: WorkspacePath | None


class _ProjectConfigModule(Protocol):
    """Deferred project config loader used without creating an import cycle."""

    def load_generated_project_config(self, root: Path) -> _GeneratedProjectConfig:
        """Load generated project config."""
        ...


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

    project_config = cast(
        "_ProjectConfigModule",
        importlib.import_module("scaffold_guard.project_config"),
    )
    try:
        generated_config = project_config.load_generated_project_config(root)
    except ValueError:
        return CheckResult(id="config-consistency", findings=())
    config = load_scaffold_guard_toml(root)
    agents = table_value(config, "agents")
    project = table_value(config, "project")

    findings.extend(_check_agent_file_consistency(root, agents))
    if pyproject_path.exists():
        pyproject_text = pyproject_path.read_text(encoding="utf-8", errors="replace")
        findings.extend(_check_coverage(project, pyproject_text))
        findings.extend(_check_python_min(project, pyproject_text))
        findings.extend(_check_lockfile_mtime(root))
    if (
        generated_config.profile == "monorepo"
        and generated_config.python_workspace is not None
        and generated_config.typescript_workspace is not None
    ):
        findings.extend(
            _check_monorepo_structured_config(
                root,
                package=generated_config.package,
                python_workspace=generated_config.python_workspace.path,
                typescript_workspace=generated_config.typescript_workspace.path,
                pyright_enabled=generated_config.pyright,
                biome_enabled=generated_config.biome,
            )
        )
    vitest_paths = [Path("vitest.config.ts")]
    if generated_config.profile == "monorepo" and generated_config.typescript_workspace is not None:
        vitest_paths.append(generated_config.typescript_workspace.path / "vitest.config.ts")
    for relative_path in vitest_paths:
        vitest_path = root / relative_path
        if vitest_path.exists():
            vitest_text = vitest_path.read_text(encoding="utf-8", errors="replace")
            findings.extend(_check_typescript_coverage(project, relative_path, vitest_text))
    return CheckResult(id="config-consistency", findings=tuple(findings))


def _check_monorepo_structured_config(
    root: Path,
    *,
    package: str,
    python_workspace: Path,
    typescript_workspace: Path,
    pyright_enabled: bool,
    biome_enabled: bool,
) -> list[CheckFinding]:
    """Verify structured package config uses the recorded workspace paths."""
    findings = _check_monorepo_pyproject(
        root,
        package=package,
        python_workspace=python_workspace,
    )
    if pyright_enabled:
        findings.extend(
            _check_monorepo_pyright(
                root,
                python_workspace=python_workspace,
            )
        )
    if biome_enabled:
        findings.extend(
            _check_monorepo_biome(
                root,
                typescript_workspace=typescript_workspace,
            )
        )
    return findings


def _check_monorepo_pyproject(
    root: Path,
    *,
    package: str,
    python_workspace: Path,
) -> list[CheckFinding]:
    """Verify Python package config targets the configured workspace."""
    relative_path = Path("pyproject.toml")
    config_path = root / relative_path
    if not config_path.exists():
        return []
    try:
        config = load_toml(config_path)
    except (OSError, UnicodeError, ValueError):
        return [_invalid_structured_config_finding(relative_path, format_name="TOML")]

    workspace = python_workspace.as_posix()
    required_values = (
        (
            ("tool", "hatch", "build", "targets", "wheel", "packages"),
            f"{workspace}/src/{package}",
        ),
        (("tool", "pytest", "ini_options", "testpaths"), f"{workspace}/tests"),
        (("tool", "pytest", "ini_options", "pythonpath"), f"{workspace}/src"),
    )
    if all(
        _string_list(_nested_value(config, keys)) == (expected,)
        for keys, expected in required_values
    ):
        return []
    return [_workspace_config_finding(relative_path, workspace)]


def _check_monorepo_pyright(
    root: Path,
    *,
    python_workspace: Path,
) -> list[CheckFinding]:
    """Verify Pyright include and import paths target the Python workspace."""
    relative_path = Path("pyrightconfig.json")
    config = _load_json_mapping(root, relative_path)
    if config is None:
        return (
            []
            if not (root / relative_path).exists()
            else [_invalid_structured_config_finding(relative_path, format_name="JSON")]
        )

    workspace = python_workspace.as_posix()
    expected_includes = {
        f"{workspace}/src",
        f"{workspace}/tests",
        f"{workspace}/examples",
    }
    includes = set(_string_list(config.get("include")))
    environments = config.get("executionEnvironments")
    extra_paths: set[str] = set()
    if isinstance(environments, list):
        for environment in cast("list[object]", environments):
            if isinstance(environment, Mapping):
                extra_paths.update(
                    _string_list(cast("Mapping[str, object]", environment).get("extraPaths"))
                )
    if includes == expected_includes and extra_paths == {f"{workspace}/src"}:
        return []
    return [_workspace_config_finding(relative_path, workspace)]


def _check_monorepo_biome(
    root: Path,
    *,
    typescript_workspace: Path,
) -> list[CheckFinding]:
    """Verify Biome include paths target the TypeScript workspace."""
    relative_path = Path("biome.json")
    config = _load_json_mapping(root, relative_path)
    if config is None:
        return (
            []
            if not (root / relative_path).exists()
            else [_invalid_structured_config_finding(relative_path, format_name="JSON")]
        )

    workspace = typescript_workspace.as_posix()
    expected_includes = {
        f"{workspace}/**",
        f"!{workspace}/dist",
        f"!{workspace}/coverage",
    }
    includes = set(_string_list(_nested_value(config, ("files", "includes"))))
    if includes == expected_includes:
        return []
    return [_workspace_config_finding(relative_path, workspace)]


def _load_json_mapping(root: Path, relative_path: Path) -> Mapping[str, object] | None:
    """Load a JSON object, returning none for missing or invalid content."""
    path = root / relative_path
    if not path.exists():
        return None
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    return cast("Mapping[str, object]", payload)


def _nested_value(config: Mapping[str, object], keys: tuple[str, ...]) -> object | None:
    """Return a value from nested mapping keys."""
    value: object = config
    for key in keys:
        value = _object_mapping(value).get(key)
    return value


def _string_list(value: object) -> tuple[str, ...]:
    """Return only string entries from a list-shaped config value."""
    if not isinstance(value, list):
        return ()
    return tuple(item for item in cast("list[object]", value) if isinstance(item, str))


def _workspace_config_finding(relative_path: Path, workspace: str) -> CheckFinding:
    """Build a structured workspace mismatch finding."""
    return finding(
        relative_path,
        line=1,
        code="monorepo-workspace-config-mismatch",
        message=f"Generated {relative_path} must reference configured workspace {workspace}.",
    )


def _invalid_structured_config_finding(
    relative_path: Path,
    *,
    format_name: str,
) -> CheckFinding:
    """Build a deterministic malformed structured-config finding."""
    return finding(
        relative_path,
        line=1,
        code="structured-config-invalid",
        message=f"Generated {relative_path} must contain valid {format_name}.",
    )


def _check_agent_file_consistency(
    root: Path,
    agents: object,
) -> list[CheckFinding]:
    """Verify selected agent booleans match generated adapter files."""
    findings: list[CheckFinding] = []
    agent_table = _object_mapping(agents)
    codex_enabled = bool_value(agent_table, "codex", default=True)
    findings.extend(_check_codex_file_consistency(root, codex_enabled))
    findings.extend(
        _check_adapter_path_consistency(
            root,
            enabled=bool_value(agent_table, "claude", default=False),
            selected_path=Path("CLAUDE.md"),
            family_path=Path(".claude"),
            adapter_name="Claude",
        )
    )
    findings.extend(
        _check_adapter_path_consistency(
            root,
            enabled=bool_value(agent_table, "cursor", default=False),
            selected_path=Path(".cursor/rules"),
            family_path=Path(".cursor"),
            adapter_name="Cursor",
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
                severity="warning",
                code="agent-config-orphan",
                message="Deselected Codex adapter files remain as upgrade orphans.",
            )
        )
    return findings


def _check_adapter_path_consistency(
    root: Path,
    *,
    enabled: bool,
    selected_path: Path,
    family_path: Path,
    adapter_name: str,
) -> list[CheckFinding]:
    """Error for a selected missing adapter and warn for deselected remnants."""
    selected_exists = (root / selected_path).exists()
    family_exists = (root / family_path).exists()
    if enabled and not selected_exists:
        return [
            finding(
                selected_path,
                line=0,
                code="agent-config-mismatch",
                message=(
                    f"scaffold-guard.toml enables {adapter_name} but {selected_path} is missing."
                ),
            )
        ]
    if not enabled and (selected_exists or family_exists):
        return [
            finding(
                family_path,
                line=0,
                severity="warning",
                code="agent-config-orphan",
                message=f"Deselected {adapter_name} adapter files remain as upgrade orphans.",
            )
        ]
    return []


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
