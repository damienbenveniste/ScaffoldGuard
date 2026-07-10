"""Packaged legacy baseline catalog for managed agent and CI files."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TypeAlias

from scaffold_guard.models import (
    AdapterSelection,
    CiChoice,
    ProfileChoice,
    normalize_adapter_selection,
)
from scaffold_guard.renderer import TemplateRenderer

LegacyRelease: TypeAlias = Literal[
    "v0.1.0",
    "v0.1.1",
    "v0.1.2",
    "v0.1.3",
    "v0.1.4",
    "v0.1.5",
]

LEGACY_RELEASES: tuple[LegacyRelease, ...] = (
    "v0.1.0",
    "v0.1.1",
    "v0.1.2",
    "v0.1.3",
    "v0.1.4",
    "v0.1.5",
)
LATEST_LEGACY_RELEASE: LegacyRelease = "v0.1.5"

_VERSION_TEMPLATE_DIRS: Mapping[LegacyRelease, str] = {
    "v0.1.0": "v0_1_0",
    "v0.1.1": "v0_1_1",
    "v0.1.2": "v0_1_2",
    "v0.1.3": "v0_1_3",
    "v0.1.4": "v0_1_4",
    "v0.1.5": "v0_1_5",
}

_RECOGNIZED_LEGACY_MANAGED_PATHS: frozenset[str] = frozenset(
    (
        "AGENTS.md",
        ".github/workflows/ci.yml",
        ".github/workflows/docs.yml",
        ".gitlab-ci.yml",
        ".codex/config.toml",
        ".codex/hooks.json",
        ".codex/agents/implementation-worker.toml",
        ".codex/agents/docs-worker.toml",
        ".codex/agents/reviewer.toml",
        ".codex/hooks/workflow-evidence.sh",
        ".codex/rules/git.rules",
        ".codex/rules/validation.rules",
        "CLAUDE.md",
        ".claude/rules/python.md",
        ".claude/rules/testing.md",
        ".claude/rules/docs.md",
        ".claude/rules/security.md",
        ".claude/rules/git-hygiene.md",
        ".claude/rules/typescript.md",
        ".cursor/rules/python.mdc",
        ".cursor/rules/testing.mdc",
        ".cursor/rules/docs.mdc",
        ".cursor/rules/security.mdc",
        ".cursor/rules/git-hygiene.mdc",
        ".cursor/rules/typescript.mdc",
    )
)


@dataclass(frozen=True, slots=True)
class LegacyCatalogConfig:
    """Inputs needed to render legacy managed-file candidates."""

    profile: ProfileChoice
    adapters: tuple[AdapterSelection, ...]
    ci: CiChoice
    render_context: Mapping[str, object]

    def __post_init__(self) -> None:
        """Normalize the exact adapter tuple to deterministic catalog order."""
        object.__setattr__(self, "adapters", normalize_adapter_selection(self.adapters))


@dataclass(frozen=True, slots=True)
class _LegacyTemplateSpec:
    """Packaged legacy template and generated destination path."""

    template_name: str
    destination: str


@dataclass(frozen=True, slots=True)
class LegacyManagedFile:
    """Rendered managed legacy file content for one generated path."""

    path: str
    content: str
    release: LegacyRelease


@dataclass(frozen=True, slots=True)
class LegacyBaselineMatch:
    """Exact global managed-file match for a legacy baseline release."""

    release: LegacyRelease
    equivalent_releases: tuple[LegacyRelease, ...]
    managed_paths: tuple[str, ...]
    desired_managed_paths: tuple[str, ...]


def desired_legacy_managed_paths(config: LegacyCatalogConfig) -> tuple[str, ...]:
    """Return latest legacy managed paths for the supplied project configuration."""
    return legacy_managed_paths(config, release=LATEST_LEGACY_RELEASE)


def legacy_managed_paths(
    config: LegacyCatalogConfig,
    *,
    release: LegacyRelease,
) -> tuple[str, ...]:
    """Return generated managed agent and CI paths for a legacy release."""
    return tuple(spec.destination for spec in _legacy_template_specs(config, release=release))


def render_legacy_managed_files(
    config: LegacyCatalogConfig,
    *,
    release: LegacyRelease,
    renderer: TemplateRenderer | None = None,
) -> tuple[LegacyManagedFile, ...]:
    """Render managed agent and CI file candidates for one legacy release."""
    active_renderer = renderer or TemplateRenderer()
    release_dir = _VERSION_TEMPLATE_DIRS[release]
    return tuple(
        LegacyManagedFile(
            path=spec.destination,
            content=active_renderer.render(
                f"legacy/{release_dir}/{spec.template_name}",
                config.render_context,
            ),
            release=release,
        )
        for spec in _legacy_template_specs(config, release=release)
    )


def identify_legacy_baseline(
    files: Mapping[str, str],
    config: LegacyCatalogConfig,
    *,
    renderer: TemplateRenderer | None = None,
) -> LegacyBaselineMatch | None:
    """Identify the newest exact, complete managed-file baseline, or return `None`.

    Unrelated project files are ignored, but every path recognized by this legacy
    catalog must exactly equal the path set and rendered bytes of one release.
    """
    active_renderer = renderer or TemplateRenderer()
    recognized_paths = frozenset(files).intersection(_RECOGNIZED_LEGACY_MANAGED_PATHS)
    matches: list[LegacyRelease] = []
    release_paths: dict[LegacyRelease, tuple[str, ...]] = {}
    for release in LEGACY_RELEASES:
        rendered_files = render_legacy_managed_files(
            config,
            release=release,
            renderer=active_renderer,
        )
        if not rendered_files:
            continue
        expected = {file.path: file.content for file in rendered_files}
        if recognized_paths != frozenset(expected):
            continue
        if all(files.get(path) == content for path, content in expected.items()):
            matches.append(release)
            release_paths[release] = tuple(expected)

    if not matches:
        return None

    newest_release = matches[-1]
    return LegacyBaselineMatch(
        release=newest_release,
        equivalent_releases=tuple(matches),
        managed_paths=release_paths[newest_release],
        desired_managed_paths=desired_legacy_managed_paths(config),
    )


def _legacy_template_specs(
    config: LegacyCatalogConfig,
    *,
    release: LegacyRelease,
) -> tuple[_LegacyTemplateSpec, ...]:
    """Return legacy managed template specs for the configured generated surface."""
    if release == "v0.1.0":
        return _v0_1_0_template_specs(config)
    return (
        *_profile_template_specs(config),
        *_agent_template_specs(config, include_codex_files=True),
    )


def _v0_1_0_template_specs(config: LegacyCatalogConfig) -> tuple[_LegacyTemplateSpec, ...]:
    """Return the narrower managed surface generated by v0.1.0."""
    if _canonical_profile(config.profile) != "python" or config.ci != "github":
        return ()
    return (
        _LegacyTemplateSpec("package/AGENTS.md.j2", "AGENTS.md"),
        _LegacyTemplateSpec("package/github/workflows/ci.yml.j2", ".github/workflows/ci.yml"),
        _LegacyTemplateSpec(
            "package/github/workflows/docs.yml.j2",
            ".github/workflows/docs.yml",
        ),
        *_agent_template_specs(config, include_codex_files=False),
    )


def _profile_template_specs(config: LegacyCatalogConfig) -> tuple[_LegacyTemplateSpec, ...]:
    """Return profile-level AGENTS and selected CI templates."""
    template_profile = _template_profile(config.profile)
    specs: tuple[_LegacyTemplateSpec, ...] = (
        _LegacyTemplateSpec(f"{template_profile}/AGENTS.md.j2", "AGENTS.md"),
    )
    if config.ci == "gitlab":
        return (
            *specs,
            _LegacyTemplateSpec(f"{template_profile}/gitlab-ci.yml.j2", ".gitlab-ci.yml"),
        )

    github_specs: tuple[_LegacyTemplateSpec, ...] = (
        _LegacyTemplateSpec(
            f"{template_profile}/github/workflows/ci.yml.j2",
            ".github/workflows/ci.yml",
        ),
    )
    if _canonical_profile(config.profile) == "python":
        github_specs = (
            *github_specs,
            _LegacyTemplateSpec(
                "package/github/workflows/docs.yml.j2",
                ".github/workflows/docs.yml",
            ),
        )
    return (*specs, *github_specs)


def _agent_template_specs(
    config: LegacyCatalogConfig,
    *,
    include_codex_files: bool,
) -> tuple[_LegacyTemplateSpec, ...]:
    """Return selected legacy agent adapter templates."""
    specs: list[_LegacyTemplateSpec] = []
    if include_codex_files and "codex" in config.adapters:
        specs.extend(
            (
                _LegacyTemplateSpec("agents/codex/config.toml.j2", ".codex/config.toml"),
                _LegacyTemplateSpec("agents/codex/hooks.json.j2", ".codex/hooks.json"),
                _LegacyTemplateSpec(
                    "agents/codex/agents/implementation-worker.toml.j2",
                    ".codex/agents/implementation-worker.toml",
                ),
                _LegacyTemplateSpec(
                    "agents/codex/agents/docs-worker.toml.j2",
                    ".codex/agents/docs-worker.toml",
                ),
                _LegacyTemplateSpec(
                    "agents/codex/agents/reviewer.toml.j2",
                    ".codex/agents/reviewer.toml",
                ),
                _LegacyTemplateSpec(
                    "agents/codex/hooks/workflow-evidence.sh.j2",
                    ".codex/hooks/workflow-evidence.sh",
                ),
                _LegacyTemplateSpec("agents/codex/rules/git.rules.j2", ".codex/rules/git.rules"),
                _LegacyTemplateSpec(
                    "agents/codex/rules/validation.rules.j2",
                    ".codex/rules/validation.rules",
                ),
            )
        )
    if "claude" in config.adapters:
        specs.extend(_claude_template_specs(config))
    if "cursor" in config.adapters:
        specs.extend(_cursor_template_specs(config))
    return tuple(specs)


def _claude_template_specs(config: LegacyCatalogConfig) -> tuple[_LegacyTemplateSpec, ...]:
    """Return legacy Claude Code adapter template specs."""
    specs: tuple[_LegacyTemplateSpec, ...] = (
        _LegacyTemplateSpec("agents/claude/CLAUDE.md.j2", "CLAUDE.md"),
        _LegacyTemplateSpec("agents/claude/rules/testing.md.j2", ".claude/rules/testing.md"),
        _LegacyTemplateSpec("agents/claude/rules/docs.md.j2", ".claude/rules/docs.md"),
        _LegacyTemplateSpec("agents/claude/rules/security.md.j2", ".claude/rules/security.md"),
        _LegacyTemplateSpec(
            "agents/claude/rules/git-hygiene.md.j2",
            ".claude/rules/git-hygiene.md",
        ),
    )
    if _includes_python(config.profile):
        specs = (
            specs[0],
            _LegacyTemplateSpec(
                "agents/claude/rules/python.md.j2",
                ".claude/rules/python.md",
            ),
            *specs[1:],
        )
    if _includes_typescript(config.profile):
        specs = (
            *specs,
            _LegacyTemplateSpec(
                "agents/claude/rules/typescript.md.j2",
                ".claude/rules/typescript.md",
            ),
        )
    return specs


def _cursor_template_specs(config: LegacyCatalogConfig) -> tuple[_LegacyTemplateSpec, ...]:
    """Return legacy Cursor adapter template specs."""
    specs: tuple[_LegacyTemplateSpec, ...] = (
        _LegacyTemplateSpec("agents/cursor/rules/testing.mdc.j2", ".cursor/rules/testing.mdc"),
        _LegacyTemplateSpec("agents/cursor/rules/docs.mdc.j2", ".cursor/rules/docs.mdc"),
        _LegacyTemplateSpec("agents/cursor/rules/security.mdc.j2", ".cursor/rules/security.mdc"),
        _LegacyTemplateSpec(
            "agents/cursor/rules/git-hygiene.mdc.j2",
            ".cursor/rules/git-hygiene.mdc",
        ),
    )
    if _includes_python(config.profile):
        specs = (
            _LegacyTemplateSpec("agents/cursor/rules/python.mdc.j2", ".cursor/rules/python.mdc"),
            *specs,
        )
    if _includes_typescript(config.profile):
        specs = (
            *specs,
            _LegacyTemplateSpec(
                "agents/cursor/rules/typescript.mdc.j2",
                ".cursor/rules/typescript.mdc",
            ),
        )
    return specs


def _template_profile(profile: ProfileChoice) -> str:
    """Return the legacy template directory name for a canonical profile."""
    canonical = _canonical_profile(profile)
    if canonical == "python":
        return "package"
    return canonical


def _canonical_profile(profile: ProfileChoice) -> str:
    """Return the canonical profile value used by legacy release metadata."""
    return "python" if profile == "package" else profile


def _includes_python(profile: ProfileChoice) -> bool:
    """Return whether the legacy generated profile includes Python files."""
    return _canonical_profile(profile) in {"python", "monorepo"}


def _includes_typescript(profile: ProfileChoice) -> bool:
    """Return whether the legacy generated profile includes TypeScript files."""
    return _canonical_profile(profile) in {"typescript", "monorepo"}
