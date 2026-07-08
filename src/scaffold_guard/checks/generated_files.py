"""Checks for generated file content."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from scaffold_guard.checks.base import CheckFinding, CheckResult, finding
from scaffold_guard.checks.config import (
    github_actions_enabled,
    gitlab_ci_enabled,
    project_profile,
    tool_enabled,
)
from scaffold_guard.checks.files import iter_text_files, read_lines, relative_to_root

AGENT_FILE_PATHS = (
    Path("AGENTS.md"),
    Path("CLAUDE.md"),
    Path(".codex"),
    Path(".claude/rules"),
    Path(".cursor/rules"),
)
PACKAGE_BASE_CI_TOKENS = ("uv sync", "pytest", "mkdocs")
MINIMAL_CI_TOKENS = ("uv tool install scaffold-guard", "scaffold-guard check")
TYPESCRIPT_CI_TOKENS = (
    "uv tool install scaffold-guard",
    "npm install",
    "npm run typecheck",
    "npm run build",
    "scaffold-guard check",
)
MONOREPO_CI_TOKENS = (
    "uv sync",
    "pytest",
    "npm install",
    "npm run ts:typecheck",
    "npm run ts:build",
)


def check_generated_files(root: Path) -> CheckResult:
    """Verify generated files do not contain unresolved template or format issues."""
    findings: list[CheckFinding] = []
    findings.extend(_check_unresolved_agent_placeholders(root))
    findings.extend(_check_codex_rules(root))
    findings.extend(_check_codex_hooks(root))
    findings.extend(_check_cursor_frontmatter(root))
    findings.extend(_check_readme_mentions_uv(root))
    findings.extend(_check_ci_workflow(root))
    return CheckResult(id="generated-files", findings=tuple(findings))


def _check_unresolved_agent_placeholders(root: Path) -> list[CheckFinding]:
    """Report unresolved Jinja placeholders in generated agent instruction files."""
    findings: list[CheckFinding] = []
    for path in iter_text_files(root, AGENT_FILE_PATHS):
        relative_path = relative_to_root(root, path)
        for line_number, line in enumerate(read_lines(path), start=1):
            if "{{" in line or "{%" in line:
                findings.append(
                    finding(
                        relative_path,
                        line=line_number,
                        code="unresolved-template-placeholder",
                        message="Generated agent file contains an unresolved template placeholder.",
                    )
                )
    return findings


def _check_codex_rules(root: Path) -> list[CheckFinding]:
    """Check Codex project rules use `.rules` files with prefix rules."""
    rules_dir = root / ".codex/rules"
    if not rules_dir.exists():
        return []
    findings: list[CheckFinding] = []
    for path in sorted(rules_dir.iterdir()):
        if not path.is_file():
            continue
        relative_path = path.relative_to(root)
        if path.suffix != ".rules":
            findings.append(
                finding(
                    relative_path,
                    line=0,
                    code="codex-rule-extension",
                    message="Codex command rules must use the .rules extension.",
                )
            )
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        if "prefix_rule(" not in content:
            findings.append(
                finding(
                    relative_path,
                    line=1,
                    code="codex-rule-missing-prefix-rule",
                    message="Codex command rules must define at least one prefix_rule.",
                )
            )
    return findings


def _check_codex_hooks(root: Path) -> list[CheckFinding]:
    """Check Codex hooks use the documented JSON hook shape."""
    hooks_path = root / ".codex/hooks.json"
    if not hooks_path.exists():
        return []
    relative_path = Path(".codex/hooks.json")
    try:
        payload: object = json.loads(hooks_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [
            finding(
                relative_path,
                line=exc.lineno,
                code="codex-hooks-json",
                message="Codex hooks must be valid JSON.",
            )
        ]
    if not isinstance(payload, Mapping):
        return [
            finding(
                relative_path,
                line=1,
                code="codex-hooks-shape",
                message="Codex hooks must be a JSON object.",
            )
        ]
    hook_config = cast("Mapping[str, object]", payload)
    hooks = hook_config.get("hooks")
    if not isinstance(hooks, Mapping):
        return [
            finding(
                relative_path,
                line=1,
                code="codex-hooks-shape",
                message="Codex hooks must contain a hooks object.",
            )
        ]
    if not _has_scaffold_guard_post_tool_use(cast("Mapping[str, object]", hooks)):
        return [
            finding(
                relative_path,
                line=1,
                code="codex-hooks-missing-policy-check",
                message="Codex hooks must run scaffold-guard check after file-edit tool use.",
            )
        ]
    return []


def _has_scaffold_guard_post_tool_use(hooks: Mapping[str, object]) -> bool:
    """Return whether PostToolUse runs `scaffold-guard check` after edits."""
    groups = hooks.get("PostToolUse")
    if not isinstance(groups, list):
        return False
    for group in cast("list[object]", groups):
        if not isinstance(group, Mapping):
            continue
        group_mapping = cast("Mapping[str, object]", group)
        matcher = group_mapping.get("matcher")
        if not isinstance(matcher, str) or "apply_patch" not in matcher:
            continue
        handlers = group_mapping.get("hooks")
        if not isinstance(handlers, list):
            continue
        for handler in cast("list[object]", handlers):
            if not isinstance(handler, Mapping):
                continue
            handler_mapping = cast("Mapping[str, object]", handler)
            command = handler_mapping.get("command")
            if isinstance(command, str) and "scaffold-guard check" in command:
                return True
    return False


def _check_cursor_frontmatter(root: Path) -> list[CheckFinding]:
    """Check Cursor `.mdc` rule frontmatter includes useful metadata."""
    rules_dir = root / ".cursor/rules"
    if not rules_dir.exists():
        return []
    findings: list[CheckFinding] = []
    for path in sorted(rules_dir.glob("*.mdc")):
        relative_path = path.relative_to(root)
        lines = read_lines(path)
        frontmatter = _frontmatter_lines(lines)
        if not frontmatter:
            findings.append(
                finding(
                    relative_path,
                    line=1,
                    code="cursor-rule-frontmatter",
                    message="Cursor rule frontmatter must be delimited by --- lines.",
                )
            )
            continue
        keys = {line.split(":", maxsplit=1)[0].strip() for line in frontmatter if ":" in line}
        findings.extend(
            finding(
                relative_path,
                line=1,
                code="cursor-rule-metadata",
                message=f"Cursor rule frontmatter must include {required_key}.",
            )
            for required_key in ("alwaysApply", "description")
            if required_key not in keys
        )
    return findings


def _check_readme_mentions_uv(root: Path) -> list[CheckFinding]:
    """Verify generated README commands point users to the configured toolchain."""
    readme_path = root / "README.md"
    if not readme_path.exists():
        return []
    content = readme_path.read_text(encoding="utf-8", errors="replace")
    profile = project_profile(root)
    expected_tokens = _readme_tool_tokens(profile)
    missing_tokens = tuple(token for token in expected_tokens if token not in content)
    if not missing_tokens:
        return []
    return [
        finding(
            "README.md",
            line=1,
            code="readme-missing-toolchain-command",
            message=f"Generated README commands must mention {', '.join(missing_tokens)}.",
        )
    ]


def _check_ci_workflow(root: Path) -> list[CheckFinding]:
    """Verify generated CI includes the V1 toolchain commands."""
    workflow_paths = _ci_workflow_paths(root)
    if not workflow_paths:
        return []
    expected_tokens = _ci_tokens(root)
    findings: list[CheckFinding] = []
    for relative_path in workflow_paths:
        workflow_path = root / relative_path
        if not workflow_path.exists():
            continue
        content = workflow_path.read_text(encoding="utf-8", errors="replace").lower()
        findings.extend(
            finding(
                relative_path,
                line=1,
                code="ci-missing-tool",
                message=f"Generated CI must include {token}.",
            )
            for token in expected_tokens
            if token not in content
        )
    return findings


def _ci_workflow_paths(root: Path) -> tuple[Path, ...]:
    """Return generated CI workflow paths selected by config."""
    paths: list[Path] = []
    if github_actions_enabled(root):
        paths.append(Path(".github/workflows/ci.yml"))
    if gitlab_ci_enabled(root):
        paths.append(Path(".gitlab-ci.yml"))
    return tuple(paths)


def _package_ci_tokens(root: Path) -> tuple[str, ...]:
    """Return required package CI tokens for the configured toolchain."""
    tokens: list[str] = list(PACKAGE_BASE_CI_TOKENS)
    if tool_enabled(root, "ruff"):
        tokens.append("ruff")
    if tool_enabled(root, "mypy"):
        tokens.append("mypy")
    if tool_enabled(root, "pyright"):
        tokens.append("pyright")
    return tuple(tokens)


def _ci_tokens(root: Path) -> tuple[str, ...]:
    """Return required CI tokens for the configured project profile."""
    profile = project_profile(root)
    if profile == "minimal":
        return MINIMAL_CI_TOKENS
    if profile == "typescript":
        return _typescript_ci_tokens(root)
    if profile == "monorepo":
        return _monorepo_ci_tokens(root)
    return _package_ci_tokens(root)


def _typescript_ci_tokens(root: Path) -> tuple[str, ...]:
    """Return required TypeScript CI tokens for the configured toolchain."""
    tokens: list[str] = list(TYPESCRIPT_CI_TOKENS)
    if tool_enabled(root, "biome"):
        tokens.extend(("npm run format:check", "npm run lint"))
    if tool_enabled(root, "vitest"):
        tokens.extend(("npm test", "npm run coverage"))
    return tuple(tokens)


def _monorepo_ci_tokens(root: Path) -> tuple[str, ...]:
    """Return required monorepo CI tokens for the configured toolchains."""
    tokens: list[str] = list(MONOREPO_CI_TOKENS)
    if tool_enabled(root, "ruff"):
        tokens.append("ruff")
    if tool_enabled(root, "mypy"):
        tokens.append("mypy")
    if tool_enabled(root, "pyright"):
        tokens.append("pyright")
    if tool_enabled(root, "biome"):
        tokens.extend(("npm run ts:format:check", "npm run ts:lint"))
    if tool_enabled(root, "vitest"):
        tokens.extend(("npm run ts:test", "npm run ts:coverage"))
    return tuple(tokens)


def _readme_tool_tokens(profile: str) -> tuple[str, ...]:
    """Return README command tokens required for the generated project profile."""
    if profile == "typescript":
        return ("npm ",)
    if profile == "monorepo":
        return ("uv ", "npm ")
    if profile == "minimal":
        return ("scaffold-guard ",)
    return ("uv ",)


def _frontmatter_lines(lines: list[str]) -> list[str]:
    """Return frontmatter lines between leading --- delimiters."""
    if not lines or lines[0] != "---":
        return []
    for index, line in enumerate(lines[1:], start=1):
        if line == "---":
            return lines[1:index]
    return []
