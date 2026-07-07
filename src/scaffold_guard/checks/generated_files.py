"""Checks for generated file content."""

from pathlib import Path

from scaffold_guard.checks.base import CheckFinding, CheckResult, finding
from scaffold_guard.checks.config import ci_enabled, project_profile, tool_enabled
from scaffold_guard.checks.files import iter_text_files, read_lines, relative_to_root

AGENT_FILE_PATHS = (
    Path("AGENTS.md"),
    Path("CLAUDE.md"),
    Path(".claude/rules"),
    Path(".cursor/rules"),
)
PACKAGE_BASE_CI_TOKENS = ("uv sync", "pytest", "mkdocs")
MINIMAL_CI_TOKENS = ("uv tool install scaffold-guard", "scaffold-guard check")


def check_generated_files(root: Path) -> CheckResult:
    """Verify generated files do not contain unresolved template or format issues."""
    findings: list[CheckFinding] = []
    findings.extend(_check_unresolved_agent_placeholders(root))
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
    """Verify generated README commands point users to uv."""
    readme_path = root / "README.md"
    if not readme_path.exists():
        return []
    content = readme_path.read_text(encoding="utf-8", errors="replace")
    if "uv " in content:
        return []
    return [
        finding(
            "README.md",
            line=1,
            code="readme-missing-uv",
            message="Generated README commands must mention uv.",
        )
    ]


def _check_ci_workflow(root: Path) -> list[CheckFinding]:
    """Verify generated CI includes the V1 toolchain commands."""
    if not ci_enabled(root):
        return []
    workflow_path = root / ".github/workflows/ci.yml"
    if not workflow_path.exists():
        return []
    content = workflow_path.read_text(encoding="utf-8", errors="replace").lower()
    expected_tokens = (
        MINIMAL_CI_TOKENS if project_profile(root) == "minimal" else _package_ci_tokens(root)
    )
    return [
        finding(
            ".github/workflows/ci.yml",
            line=1,
            code="ci-missing-tool",
            message=f"Generated CI must include {token}.",
        )
        for token in expected_tokens
        if token not in content
    ]


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


def _frontmatter_lines(lines: list[str]) -> list[str]:
    """Return frontmatter lines between leading --- delimiters."""
    if not lines or lines[0] != "---":
        return []
    for index, line in enumerate(lines[1:], start=1):
        if line == "---":
            return lines[1:index]
    return []
