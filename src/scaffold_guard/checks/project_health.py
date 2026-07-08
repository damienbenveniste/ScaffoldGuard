"""Generated-project health checks."""

from pathlib import Path

from scaffold_guard.checks.base import CheckFinding, CheckResult, finding
from scaffold_guard.checks.config import (
    bool_value,
    docs_enabled,
    github_actions_enabled,
    gitlab_ci_enabled,
    load_scaffold_guard_toml,
    project_profile,
    table_value,
    tool_enabled,
)

CODEX_ADAPTER_PATHS = (
    Path(".codex/config.toml"),
    Path(".codex/hooks.json"),
    Path(".codex/rules/git.rules"),
    Path(".codex/rules/validation.rules"),
)


def check_project_health(root: Path) -> CheckResult:
    """Verify required generated-project files and adapter health."""
    findings: list[CheckFinding] = []
    findings.extend(_missing_required_paths(root))
    findings.extend(_check_codex_adapter(root))
    findings.extend(_check_claude_wrapper(root))
    findings.extend(_check_cursor_rules(root))
    return CheckResult(id="project-health", findings=tuple(findings))


def _missing_required_paths(root: Path) -> list[CheckFinding]:
    """Return findings for missing required project paths."""
    required_paths = [
        Path("AGENTS.md"),
        Path("scaffold-guard.toml"),
    ]
    profile = project_profile(root)
    if profile == "python":
        required_paths.extend(_package_required_paths(root))
    if profile == "typescript":
        required_paths.extend(_typescript_required_paths(root))
    if profile == "monorepo":
        required_paths.extend(_monorepo_required_paths(root))
    if github_actions_enabled(root):
        required_paths.append(Path(".github/workflows/ci.yml"))
    if gitlab_ci_enabled(root):
        required_paths.append(Path(".gitlab-ci.yml"))

    return [
        finding(
            relative_path,
            line=0,
            code="missing-required-path",
            message=f"Required generated project path is missing: {relative_path}",
        )
        for relative_path in required_paths
        if not (root / relative_path).exists()
    ]


def _check_codex_adapter(root: Path) -> list[CheckFinding]:
    """Verify selected Codex adapter files exist and have expected extensions."""
    if not (root / "scaffold-guard.toml").exists():
        return []
    config = load_scaffold_guard_toml(root)
    agents = table_value(config, "agents")
    if not bool_value(agents, "codex", default=True):
        return []
    findings = [
        finding(
            relative_path,
            line=0,
            code="missing-required-path",
            message=f"Required Codex adapter path is missing: {relative_path}",
        )
        for relative_path in CODEX_ADAPTER_PATHS
        if not (root / relative_path).exists()
    ]
    rules_dir = root / ".codex/rules"
    if not rules_dir.exists():
        return findings
    findings.extend(
        finding(
            path.relative_to(root),
            line=0,
            code="codex-rule-extension",
            message="Codex project rules must use the .rules extension.",
        )
        for path in sorted(rules_dir.iterdir())
        if path.is_file() and path.suffix != ".rules"
    )
    return findings


def _package_required_paths(root: Path) -> list[Path]:
    """Return required paths for generated Python package projects."""
    paths = [
        Path("pyproject.toml"),
        Path("src"),
        Path("tests"),
    ]
    if tool_enabled(root, "pyright"):
        paths.append(Path("pyrightconfig.json"))
    if docs_enabled(root):
        paths.extend((Path("docs"), Path("mkdocs.yml")))
    return paths


def _typescript_required_paths(root: Path) -> list[Path]:
    """Return required paths for generated TypeScript package projects."""
    paths = [
        Path("package.json"),
        Path("tsconfig.json"),
        Path("tsconfig.build.json"),
        Path("src"),
    ]
    if tool_enabled(root, "biome"):
        paths.append(Path("biome.json"))
    if tool_enabled(root, "vitest"):
        paths.extend((Path("vitest.config.ts"), Path("tests")))
    return paths


def _monorepo_required_paths(root: Path) -> list[Path]:
    """Return required paths for generated Python and TypeScript monorepos."""
    paths = [
        Path("pyproject.toml"),
        Path("package.json"),
        Path("packages/python/src"),
        Path("packages/python/tests"),
        Path("packages/typescript/package.json"),
        Path("packages/typescript/tsconfig.json"),
        Path("packages/typescript/tsconfig.build.json"),
        Path("packages/typescript/src"),
    ]
    if tool_enabled(root, "biome"):
        paths.append(Path("biome.json"))
    if tool_enabled(root, "vitest"):
        paths.extend(
            (Path("packages/typescript/vitest.config.ts"), Path("packages/typescript/tests"))
        )
    if tool_enabled(root, "pyright"):
        paths.append(Path("pyrightconfig.json"))
    return paths


def _check_claude_wrapper(root: Path) -> list[CheckFinding]:
    """Verify CLAUDE.md references the shared AGENTS.md source."""
    claude_path = root / "CLAUDE.md"
    if not claude_path.exists():
        return []
    content = claude_path.read_text(encoding="utf-8", errors="replace")
    if "AGENTS.md" in content:
        return []
    return [
        finding(
            "CLAUDE.md",
            line=1,
            code="claude-missing-agents-reference",
            message="CLAUDE.md must import or reference AGENTS.md.",
        )
    ]


def _check_cursor_rules(root: Path) -> list[CheckFinding]:
    """Verify Cursor rule files use `.mdc` and have frontmatter."""
    rules_dir = root / ".cursor/rules"
    if not rules_dir.exists():
        return []
    findings: list[CheckFinding] = []
    for path in sorted(rules_dir.iterdir()):
        if not path.is_file():
            continue
        relative_path = path.relative_to(root)
        if path.suffix != ".mdc":
            findings.append(
                finding(
                    relative_path,
                    line=0,
                    code="cursor-rule-extension",
                    message="Cursor project rules must use the .mdc extension.",
                )
            )
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        if not content.startswith("---\n"):
            findings.append(
                finding(
                    relative_path,
                    line=1,
                    code="cursor-rule-frontmatter",
                    message="Cursor project rules must start with frontmatter.",
                )
            )
    return findings
