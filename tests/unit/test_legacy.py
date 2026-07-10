"""Tests for packaged legacy managed-file baseline recognition."""

from pathlib import Path

import pytest

from scaffold_guard.legacy import (
    LEGACY_RELEASES,
    LegacyCatalogConfig,
    LegacyRelease,
    desired_legacy_managed_paths,
    identify_legacy_baseline,
    legacy_managed_paths,
    render_legacy_managed_files,
)
from scaffold_guard.models import (
    AdapterSelection,
    CiChoice,
    InitOptions,
    ProfileChoice,
    normalize_profile_choice,
)
from scaffold_guard.scaffold import build_render_context

_RECOGNITION_CONFIGS: dict[
    LegacyRelease,
    tuple[ProfileChoice, tuple[AdapterSelection, ...], CiChoice],
] = {
    "v0.1.0": ("python", ("codex", "claude", "cursor"), "github"),
    "v0.1.1": ("minimal", ("codex", "claude"), "github"),
    "v0.1.2": ("python", ("claude", "cursor"), "gitlab"),
    "v0.1.3": ("typescript", ("codex", "cursor"), "github"),
    "v0.1.4": ("monorepo", ("codex", "claude", "cursor"), "gitlab"),
    "v0.1.5": ("typescript", ("claude", "cursor"), "gitlab"),
}


@pytest.mark.parametrize("release", LEGACY_RELEASES)
def test_legacy_catalog_recognizes_every_packaged_release(
    tmp_path: Path,
    release: LegacyRelease,
) -> None:
    """Every packaged release participates in exact baseline recognition."""
    profile, adapters, ci = _RECOGNITION_CONFIGS[release]
    config = _legacy_config(
        tmp_path,
        release_profile=profile,
        adapters=adapters,
        ci=ci,
    )
    rendered_files = render_legacy_managed_files(config, release=release)
    files = {file.path: file.content for file in rendered_files}

    match = identify_legacy_baseline(files, config)

    assert match is not None
    assert release in match.equivalent_releases
    assert match.managed_paths == tuple(files)


def test_legacy_catalog_renders_and_matches_v0_1_0_package_baseline(tmp_path: Path) -> None:
    """The oldest packaged legacy release can be recognized exactly."""
    config = _legacy_config(
        tmp_path,
        release_profile="python",
        adapters=("codex", "claude", "cursor"),
        ci="github",
    )
    rendered_files = render_legacy_managed_files(config, release="v0.1.0")
    files = {file.path: file.content for file in rendered_files}

    match = identify_legacy_baseline(files, config)

    assert match is not None
    assert match.release == "v0.1.0"
    assert match.managed_paths == tuple(files)
    assert ".github/workflows/docs.yml" in match.managed_paths
    assert ".codex/config.toml" not in match.managed_paths


def test_legacy_catalog_identifies_newest_equivalent_v0_1_5_baseline(tmp_path: Path) -> None:
    """Exact content shared by v0.1.4 and v0.1.5 resolves to the latest baseline."""
    config = _legacy_config(
        tmp_path,
        release_profile="typescript",
        adapters=("codex", "claude", "cursor"),
        ci="gitlab",
    )
    rendered_files = render_legacy_managed_files(config, release="v0.1.5")
    files = {file.path: file.content for file in rendered_files}

    match = identify_legacy_baseline(files, config)

    assert match is not None
    assert match.release == "v0.1.5"
    assert match.equivalent_releases[-2:] == ("v0.1.4", "v0.1.5")
    assert match.managed_paths == tuple(files)
    assert match.desired_managed_paths == desired_legacy_managed_paths(config)
    assert ".claude/rules/typescript.md" in match.managed_paths
    assert ".claude/rules/python.md" not in match.managed_paths
    assert ".gitlab-ci.yml" in match.managed_paths


@pytest.mark.parametrize(
    ("adapters", "expected_paths", "unexpected_paths"),
    [
        (
            ("codex", "claude"),
            {".codex/config.toml", "CLAUDE.md"},
            {".cursor/rules/python.mdc"},
        ),
        (
            ("codex", "cursor"),
            {".codex/config.toml", ".cursor/rules/python.mdc"},
            {"CLAUDE.md"},
        ),
        (
            ("claude", "cursor"),
            {"CLAUDE.md", ".cursor/rules/python.mdc"},
            {".codex/config.toml"},
        ),
    ],
)
def test_legacy_catalog_preserves_exact_non_shorthand_adapter_combinations(
    tmp_path: Path,
    adapters: tuple[AdapterSelection, ...],
    expected_paths: set[str],
    unexpected_paths: set[str],
) -> None:
    """Legacy rendering neither adds nor removes adapters from an exact selection."""
    config = _legacy_config(
        tmp_path,
        release_profile="python",
        adapters=adapters,
        ci="github",
    )
    rendered_files = render_legacy_managed_files(config, release="v0.1.5")
    files = {file.path: file.content for file in rendered_files}

    assert expected_paths <= files.keys()
    assert files.keys().isdisjoint(unexpected_paths)
    assert identify_legacy_baseline(files, config) is not None


def test_legacy_catalog_rejects_missing_expected_managed_file(tmp_path: Path) -> None:
    """A partial managed-file surface cannot be globally adopted."""
    config = _legacy_config(
        tmp_path,
        release_profile="python",
        adapters=("codex", "claude"),
        ci="github",
    )
    rendered_files = render_legacy_managed_files(config, release="v0.1.5")
    files = {file.path: file.content for file in rendered_files}
    del files["CLAUDE.md"]

    assert identify_legacy_baseline(files, config) is None


def test_legacy_catalog_rejects_unexpected_recognized_managed_file(tmp_path: Path) -> None:
    """A recognized adapter path outside the configured surface prevents adoption."""
    config = _legacy_config(
        tmp_path,
        release_profile="python",
        adapters=("codex", "claude"),
        ci="github",
    )
    rendered_files = render_legacy_managed_files(config, release="v0.1.5")
    files = {file.path: file.content for file in rendered_files}
    cursor_config = _legacy_config(
        tmp_path,
        release_profile="python",
        adapters=("cursor",),
        ci="github",
    )
    cursor_files = {
        file.path: file.content
        for file in render_legacy_managed_files(cursor_config, release="v0.1.5")
    }
    files[".cursor/rules/python.mdc"] = cursor_files[".cursor/rules/python.mdc"]

    assert identify_legacy_baseline(files, config) is None


def test_legacy_catalog_rejects_one_byte_managed_file_edit(tmp_path: Path) -> None:
    """Any byte-level edit in a managed legacy file prevents a baseline match."""
    config = _legacy_config(
        tmp_path,
        release_profile="python",
        adapters=("codex",),
        ci="github",
    )
    rendered_files = render_legacy_managed_files(config, release="v0.1.5")
    files = {file.path: file.content for file in rendered_files}
    files[".github/workflows/ci.yml"] = f"{files['.github/workflows/ci.yml']} "

    assert identify_legacy_baseline(files, config) is None


def test_legacy_catalog_rejects_marker_preserving_managed_file_edit(tmp_path: Path) -> None:
    """Generated markers alone are not enough; content must be exact."""
    config = _legacy_config(
        tmp_path,
        release_profile="python",
        adapters=("codex", "claude", "cursor"),
        ci="github",
    )
    rendered_files = render_legacy_managed_files(config, release="v0.1.5")
    files = {file.path: file.content for file in rendered_files}
    files["AGENTS.md"] = files["AGENTS.md"].replace(
        "Keep generated projects on Python `3.13` or newer.",
        "Keep generated projects on Python `3.13` or newer when practical.",
    )

    assert "<!-- generated by scaffold-guard;" in files["AGENTS.md"]
    assert identify_legacy_baseline(files, config) is None


def test_legacy_managed_paths_follow_profile_adapters_and_ci(tmp_path: Path) -> None:
    """Managed paths are deterministic and limited to the configured generated surface."""
    config = _legacy_config(
        tmp_path,
        release_profile="minimal",
        adapters=("codex",),
        ci="github",
    )

    assert legacy_managed_paths(config, release="v0.1.0") == ()
    assert legacy_managed_paths(config, release="v0.1.5") == (
        "AGENTS.md",
        ".github/workflows/ci.yml",
        ".codex/config.toml",
        ".codex/hooks.json",
        ".codex/agents/implementation-worker.toml",
        ".codex/agents/docs-worker.toml",
        ".codex/agents/reviewer.toml",
        ".codex/hooks/workflow-evidence.sh",
        ".codex/rules/git.rules",
        ".codex/rules/validation.rules",
    )
    assert LEGACY_RELEASES == (
        "v0.1.0",
        "v0.1.1",
        "v0.1.2",
        "v0.1.3",
        "v0.1.4",
        "v0.1.5",
    )


def _legacy_config(
    tmp_path: Path,
    *,
    release_profile: ProfileChoice,
    adapters: tuple[AdapterSelection, ...],
    ci: CiChoice,
) -> LegacyCatalogConfig:
    canonical_profile = normalize_profile_choice(release_profile)
    python_quality_enabled = canonical_profile not in {"minimal", "typescript"}
    options = InitOptions(
        target_dir=tmp_path / "demo-project",
        project_slug="demo-project",
        package_name="demo_project",
        agent="codex",
        profile=canonical_profile,
        license="MIT",
        python_min="3.13",
        coverage=95,
        ci=ci,
        docs_enabled=canonical_profile == "python",
        dry_run=True,
        force=False,
        ruff_enabled=python_quality_enabled,
        mypy_enabled=python_quality_enabled,
        pyright_enabled=python_quality_enabled,
        ruff_mode="strict" if python_quality_enabled else "off",
        python_typecheck_mode="strict" if python_quality_enabled else "off",
        adapter_selection=adapters,
    )
    return LegacyCatalogConfig(
        profile=options.profile,
        adapters=options.adapter_selection,
        ci=options.ci,
        render_context=build_render_context(options),
    )
