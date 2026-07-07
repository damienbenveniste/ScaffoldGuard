"""Generated-project health checks."""

from pathlib import Path

from scaffold_guard.checks.base import CheckFinding, CheckResult, finding
from scaffold_guard.checks.config import ci_enabled, docs_enabled, project_profile


def check_project_health(root: Path) -> CheckResult:
    """Verify required generated-project files and adapter health."""
    findings: list[CheckFinding] = []
    findings.extend(_missing_required_paths(root))
    findings.extend(_check_claude_wrapper(root))
    findings.extend(_check_cursor_rules(root))
    return CheckResult(id="project-health", findings=tuple(findings))


def _missing_required_paths(root: Path) -> list[CheckFinding]:
    """Return findings for missing required project paths."""
    required_paths = [
        Path("AGENTS.md"),
        Path("scaffold-guard.toml"),
    ]
    if project_profile(root) == "package":
        required_paths.extend(
            [
                Path("pyproject.toml"),
                Path("pyrightconfig.json"),
                Path("src"),
                Path("tests"),
            ]
        )
        if docs_enabled(root):
            required_paths.append(Path("docs"))
    if ci_enabled(root):
        required_paths.append(Path(".github/workflows/ci.yml"))

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
