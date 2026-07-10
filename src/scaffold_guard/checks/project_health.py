"""Generated-project health checks."""

import importlib
from pathlib import Path
from typing import Protocol, cast

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
from scaffold_guard.fs import has_symlink_component
from scaffold_guard.manifest import (
    MANIFEST_RELATIVE_PATH,
    ProjectManifest,
    bytes_sha256,
    load_manifest,
)
from scaffold_guard.models import AdapterSelection, InitOptions, ProfileChoice, TemplateLifecycle

CODEX_ADAPTER_PATHS: tuple[Path, ...] = (
    Path(".codex/config.toml"),
    Path(".codex/hooks.json"),
    Path(".codex/agents/implementation-worker.toml"),
    Path(".codex/agents/docs-worker.toml"),
    Path(".codex/agents/reviewer.toml"),
    Path(".codex/hooks/workflow-evidence.sh"),
    Path(".codex/rules/git.rules"),
    Path(".codex/rules/validation.rules"),
)


class _ManifestConfig(Protocol):
    """Config fields required for manifest health checks."""

    @property
    def format_version(self) -> int | None:
        """Return the generated-project format version."""
        ...

    @property
    def generated_with(self) -> str | None:
        """Return the ScaffoldGuard version that generated the project."""
        ...

    @property
    def requires_scaffold_guard(self) -> str | None:
        """Return the generated project's runtime requirement."""
        ...

    @property
    def profile(self) -> ProfileChoice:
        """Return the configured project profile."""
        ...

    @property
    def adapters(self) -> tuple[AdapterSelection, ...]:
        """Return the exact configured adapter set."""
        ...

    @property
    def docs(self) -> bool:
        """Return whether generated documentation is enabled."""
        ...

    @property
    def github_actions(self) -> bool:
        """Return whether GitHub Actions is enabled."""
        ...

    @property
    def gitlab_ci(self) -> bool:
        """Return whether GitLab CI is enabled."""
        ...

    def to_init_options(self, *, dry_run: bool, force: bool) -> InitOptions:
        """Convert the loaded config to exact scaffold rendering options."""
        ...


class _RenderedFile(Protocol):
    """Rendered-file fields required to determine managed selection."""

    path: Path
    lifecycle: TemplateLifecycle


class _ScaffoldModule(Protocol):
    """Deferred scaffold API used without extending the config import cycle."""

    def render_package_files(self, options: InitOptions) -> tuple[_RenderedFile, ...]:
        """Render generated-project files for the supplied options."""
        ...


class _ProjectConfigModule(Protocol):
    """Deferred project_config API used without creating an import cycle."""

    def load_generated_project_config(self, root: Path) -> _ManifestConfig:
        """Load generated project config."""
        ...


def check_project_health(root: Path) -> CheckResult:
    """Verify required generated-project files and adapter health."""
    findings: list[CheckFinding] = []
    findings.extend(_check_manifest_health(root))
    findings.extend(_missing_required_paths(root))
    findings.extend(_check_codex_adapter(root))
    findings.extend(_check_claude_wrapper(root))
    findings.extend(_check_cursor_rules(root))
    return CheckResult(id="project-health", findings=tuple(findings))


def _check_manifest_health(root: Path) -> list[CheckFinding]:
    """Verify v0.2 generated-project manifest health."""
    project_config = cast(
        "_ProjectConfigModule",
        importlib.import_module("scaffold_guard.project_config"),
    )
    manifest_path = root / MANIFEST_RELATIVE_PATH
    try:
        config = project_config.load_generated_project_config(root)
    except ValueError as exc:
        return [
            finding(
                "scaffold-guard.toml",
                line=0,
                code="generated-config-invalid",
                message=str(exc),
            )
        ]
    if config.format_version is None:
        if manifest_path.exists():
            return []
        return [
            finding(
                MANIFEST_RELATIVE_PATH,
                line=0,
                severity="warning",
                code="legacy-manifest-missing",
                message="Legacy generated project has no managed-file manifest; run upgrade.",
            )
        ]
    if not manifest_path.exists():
        return [
            finding(
                MANIFEST_RELATIVE_PATH,
                line=0,
                code="manifest-missing",
                message="v0.2 generated project metadata requires a managed-file manifest.",
            )
        ]
    try:
        manifest = load_manifest(manifest_path)
    except (OSError, TypeError, ValueError) as exc:
        return [
            finding(
                MANIFEST_RELATIVE_PATH,
                line=0,
                code="manifest-invalid",
                message=f"Managed-file manifest is invalid: {exc}",
            )
        ]
    return _manifest_findings(root, config, manifest)


def _manifest_findings(
    root: Path,
    config: _ManifestConfig,
    manifest: ProjectManifest,
) -> list[CheckFinding]:
    """Return findings for a loaded manifest."""
    findings: list[CheckFinding] = []
    if (
        manifest.generated_with != config.generated_with
        or manifest.requires_scaffold_guard != config.requires_scaffold_guard
        or manifest.project_format_version != config.format_version
        or manifest.profile != config.profile
        or manifest.adapters != config.adapters
    ):
        findings.append(
            finding(
                MANIFEST_RELATIVE_PATH,
                line=0,
                code="manifest-config-mismatch",
                message="Managed-file manifest metadata does not match scaffold-guard.toml.",
            )
        )
    desired_paths = desired_managed_paths(config)
    manifest_paths = {file.path for file in manifest.files}
    findings.extend(
        finding(
            path_text,
            line=0,
            code="manifest-record-missing",
            message="Selected managed file is missing from the managed-file manifest.",
        )
        for path_text in sorted(desired_paths - manifest_paths)
    )
    for file in manifest.files:
        if file.lifecycle != "managed":
            continue
        path = Path(file.path)
        if file.path not in desired_paths:
            findings.append(_manifest_orphan_finding(root, path))
            continue
        file_finding = _manifest_file_finding(root, path, file.sha256)
        if file_finding is not None:
            findings.append(file_finding)
    return findings


def desired_managed_paths(config: _ManifestConfig) -> frozenset[str]:
    """Render and return the exact managed path set selected by current config."""
    scaffold = cast(
        "_ScaffoldModule",
        importlib.import_module("scaffold_guard.scaffold"),
    )
    rendered = scaffold.render_package_files(config.to_init_options(dry_run=True, force=False))
    return frozenset(
        file.path.as_posix()
        for file in rendered
        if file.lifecycle == "managed" and _managed_path_is_selected(file.path, config)
    )


def _managed_path_is_selected(path: Path, config: _ManifestConfig) -> bool:
    """Return whether optional managed output remains selected by current config."""
    path_text = path.as_posix()
    if path_text.startswith(".github/workflows/"):
        if not config.github_actions:
            return False
        return path_text != ".github/workflows/docs.yml" or config.docs
    if path_text == ".gitlab-ci.yml":
        return config.gitlab_ci
    return True


def _manifest_orphan_finding(root: Path, path: Path) -> CheckFinding:
    """Return a warning for a manifest record deselected by current config."""
    target = root / path
    state = "remains in place" if target.exists() or target.is_symlink() else "is already absent"
    return finding(
        path,
        line=0,
        severity="warning",
        code="manifest-file-orphan",
        message=f"Managed file is no longer selected by current configuration and {state}.",
    )


def _manifest_file_finding(root: Path, path: Path, expected_sha256: str) -> CheckFinding | None:
    """Return a manifest-file finding, if one exists."""
    target = root / path
    if has_symlink_component(root, path):
        return finding(
            path,
            line=0,
            code="manifest-file-invalid",
            message="Manifest file path contains a symbolic-link component.",
        )
    if not target.exists():
        return finding(
            path,
            line=0,
            code="manifest-file-missing",
            message="Manifest file is missing.",
        )
    if target.is_symlink() or not target.is_file():
        return finding(
            path,
            line=0,
            code="manifest-file-invalid",
            message="Manifest file is not a regular file.",
        )
    current_hash = bytes_sha256(target.read_bytes())
    if current_hash == expected_sha256:
        return None
    return finding(
        path,
        line=0,
        code="manifest-file-drift",
        message="Manifest file content differs from the recorded generated baseline.",
    )


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
