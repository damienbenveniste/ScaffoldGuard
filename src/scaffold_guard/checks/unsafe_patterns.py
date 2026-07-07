"""Unsafe-pattern policy checks."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from scaffold_guard.checks.base import CheckFinding, CheckResult, finding
from scaffold_guard.checks.config import policy_enabled
from scaffold_guard.checks.files import (
    gitignore_entries,
    iter_text_files,
    read_lines,
    relative_to_root,
)

SCAN_PATHS = (
    Path("src"),
    Path("tests"),
    Path("docs"),
    Path("examples"),
    Path("AGENTS.md"),
    Path("CLAUDE.md"),
    Path(".claude/rules"),
    Path(".cursor/rules"),
)


@dataclass(frozen=True, slots=True)
class LinePattern:
    """A line-level unsafe pattern and optional policy gate."""

    token: str
    code: str
    message: str
    policy_key: str | None = None


LINE_PATTERNS = (
    LinePattern(
        "# type: ignore",
        "no-type-ignore",
        "Do not use # type: ignore; fix the type flow.",
        "forbid_type_ignore",
    ),
    LinePattern(
        "# pyright: ignore",
        "no-pyright-ignore",
        "Do not use # pyright: ignore; fix the type flow.",
        "forbid_pyright_ignore",
    ),
    LinePattern(
        "# noqa:",
        "no-noqa",
        "Do not use # noqa suppressions; fix the lint issue.",
        "forbid_noqa",
    ),
    LinePattern(
        "dict[str, Any]",
        "no-dict-str-any",
        "Do not use dict[str, Any]; model the shape explicitly.",
        "forbid_dict_str_any",
    ),
    LinePattern(
        "OPENAI_API_KEY=sk-",
        "secret-openai-key",
        "Do not commit OpenAI API key literals.",
    ),
    LinePattern(
        "ANTHROPIC_API_KEY=",
        "secret-anthropic-key",
        "Do not commit Anthropic API key literals.",
    ),
    LinePattern(
        "AWS_SECRET_ACCESS_KEY=",
        "secret-aws-key",
        "Do not commit AWS secret key literals.",
    ),
)
TYPING_ANY_IMPORT = re.compile(r"from\s+typing\s+import\s+.*\bAny\b|import\s+typing\s+as\s+typing")
PASSWORD_LITERAL = re.compile(r"password\s*=\s*[\"'][^\"']+[\"']", flags=re.IGNORECASE)
SHELL_TRUE = re.compile(r"subprocess\.run\([^\n)]*shell\s*=\s*True")
ABSOLUTE_WRITE = re.compile(r"(?:Path\([\"']/|open\([\"']/|write_text\([\"']/|write_bytes\([\"']/)")


def check_unsafe_patterns(root: Path) -> CheckResult:
    """Find unsafe source, test, docs, example, and agent-instruction patterns."""
    findings: list[CheckFinding] = []
    policy = _policy_settings(root)
    for path in iter_text_files(root, SCAN_PATHS):
        relative_path = relative_to_root(root, path)
        findings.extend(_scan_file(relative_path, path, policy=policy))
    findings.extend(_scan_runtime_artifacts(root))
    return CheckResult(id="unsafe-patterns", findings=tuple(findings))


def _scan_file(
    relative_path: Path,
    path: Path,
    *,
    policy: frozenset[str],
) -> Iterable[CheckFinding]:
    """Scan one text file for unsafe patterns."""
    findings: list[CheckFinding] = []
    for line_number, line in enumerate(read_lines(path), start=1):
        skip_markdown_policy_text = path.suffix in {".md", ".mdc"} and "`" in line
        for pattern in LINE_PATTERNS:
            if not _line_pattern_enabled(pattern, policy):
                continue
            if pattern.token in line and not skip_markdown_policy_text:
                findings.append(
                    finding(
                        relative_path,
                        line=line_number,
                        code=pattern.code,
                        message=pattern.message,
                    )
                )
        if "forbid_any" in policy and path.suffix == ".py" and TYPING_ANY_IMPORT.search(line):
            findings.append(
                finding(
                    relative_path,
                    line=line_number,
                    code="no-any-import",
                    message="Do not import Any from typing in project code.",
                )
            )
        if PASSWORD_LITERAL.search(line):
            findings.append(
                finding(
                    relative_path,
                    line=line_number,
                    code="secret-password-literal",
                    message="Do not commit password string literals.",
                )
            )
    content = path.read_text(encoding="utf-8", errors="replace")
    findings.extend(_scan_content(relative_path, content, policy=policy))
    return findings


def _scan_content(
    relative_path: Path,
    content: str,
    *,
    policy: frozenset[str],
) -> Iterable[CheckFinding]:
    """Scan full file content for patterns that can appear on one logical line."""
    findings: list[CheckFinding] = []
    if "forbid_shell_true" in policy and SHELL_TRUE.search(content):
        findings.append(
            finding(
                relative_path,
                line=1,
                code="no-shell-true",
                message="Do not use subprocess.run with shell=True.",
            )
        )
    if relative_path.suffix == ".py" and ABSOLUTE_WRITE.search(content):
        findings.append(
            finding(
                relative_path,
                line=1,
                code="no-absolute-write",
                message="Do not write directly to absolute paths in generated scripts.",
            )
        )
    return findings


def _line_pattern_enabled(pattern: LinePattern, policy: frozenset[str]) -> bool:
    """Return whether a configured line pattern should be enforced."""
    return pattern.policy_key is None or pattern.policy_key in policy


def _policy_settings(root: Path) -> frozenset[str]:
    """Return enabled unsafe-pattern policy keys."""
    return frozenset(
        key
        for key in (
            "forbid_type_ignore",
            "forbid_pyright_ignore",
            "forbid_noqa",
            "forbid_any",
            "forbid_dict_str_any",
            "forbid_shell_true",
        )
        if policy_enabled(root, key)
    )


def _scan_runtime_artifacts(root: Path) -> Iterable[CheckFinding]:
    """Report secret/runtime artifacts that appear trackable."""
    findings: list[CheckFinding] = []
    ignored_entries = gitignore_entries(root)
    if (root / ".env").exists():
        findings.append(
            finding(
                ".env",
                line=0,
                code="no-env-file",
                message="Do not commit .env files or local credentials.",
            )
        )
    findings.extend(
        finding(
            artifact,
            line=0,
            code="no-runtime-artifact",
            message=f"Do not commit runtime artifact directory {artifact}.",
        )
        for artifact in (".venv", ".replaylab")
        if (root / artifact).exists() and artifact not in ignored_entries
    )
    return findings
