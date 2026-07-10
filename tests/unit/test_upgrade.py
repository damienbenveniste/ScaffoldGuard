"""Tests for generated-project upgrade planning."""

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Protocol, cast

import pytest
from typer.testing import CliRunner

from scaffold_guard import upgrade as upgrade_module
from scaffold_guard.checks.base import CheckReport, CheckResult, finding
from scaffold_guard.cli import app
from scaffold_guard.compile_rules import selected_agent_files
from scaffold_guard.fs import TransactionalWrite
from scaffold_guard.legacy import (
    LegacyCatalogConfig,
    render_legacy_managed_files,
)
from scaffold_guard.manifest import (
    MANIFEST_RELATIVE_PATH,
    ManifestFile,
    ProjectManifest,
    bytes_sha256,
    load_manifest,
    write_manifest,
)
from scaffold_guard.migrations import StructuredFileChange
from scaffold_guard.project_config import load_generated_project_config
from scaffold_guard.scaffold import RenderedFile, build_init_options, build_render_context
from scaffold_guard.upgrade import (
    ACTION_ORDER,
    UpgradeAction,
    UpgradeError,
    UpgradePlan,
    UpgradeResult,
    apply_upgrade_plan,
    plan_upgrade,
)

CONFIG_ERROR = 2


class _MigrationPlanner(Protocol):
    """Typed access to the internal structured planner safety boundary."""

    def __call__(
        self,
        root: Path,
        path: Path,
        current: ManifestFile | None,
        migration: StructuredFileChange,
    ) -> tuple[UpgradeAction, TransactionalWrite | None]: ...


class _LegacyMigrationPlanner(Protocol):
    """Typed access to the internal legacy structured planner."""

    def __call__(
        self,
        root: Path,
        *,
        path: Path,
        migration: StructuredFileChange,
    ) -> tuple[UpgradeAction, TransactionalWrite | None]: ...


class _AcceptedLegacyPlanner(Protocol):
    """Typed access to one accepted legacy managed-file planner."""

    def __call__(
        self,
        current: Path,
        *,
        file: RenderedFile,
        accepted: set[Path],
    ) -> tuple[UpgradeAction, TransactionalWrite | None]: ...


class _ManifestMetadataValidator(Protocol):
    """Typed access to strict config/manifest metadata validation."""

    def __call__(self, config: object, manifest: ProjectManifest) -> None: ...


def test_legacy_missing_pyproject_create_is_reported_as_add(tmp_path: Path) -> None:
    """Structured create migrations use the public add action kind."""
    project_dir = _legacy_minimal_project(tmp_path)

    plan = plan_upgrade(project_dir)
    pyproject_actions = [action for action in plan.actions if action.path == Path("pyproject.toml")]

    assert not plan.conflicts
    assert pyproject_actions
    assert pyproject_actions[0].kind == "add"


def test_exact_legacy_managed_files_do_not_require_accept_flags(tmp_path: Path) -> None:
    """Exact historical managed baselines are adopted without per-file acceptance."""
    project_dir = _legacy_minimal_project(tmp_path)

    plan = plan_upgrade(project_dir)

    assert not plan.conflicts
    assert any(
        action.kind == "update" and action.path == Path("AGENTS.md") for action in plan.actions
    )


def test_marker_preserving_legacy_edit_requires_scoped_acceptance(tmp_path: Path) -> None:
    """One edited marker-bearing legacy file conflicts until that path is accepted."""
    project_dir = _legacy_minimal_project(tmp_path)
    agents_path = project_dir / "AGENTS.md"
    agents_path.write_text(
        agents_path.read_text(encoding="utf-8").replace(
            "# Agent Instructions",
            "# Local Agent Instructions",
        ),
        encoding="utf-8",
    )

    preview = plan_upgrade(project_dir)
    accepted = plan_upgrade(project_dir, accept_legacy=(Path("AGENTS.md"),))

    assert any(
        action.kind == "conflict" and action.path == Path("AGENTS.md") for action in preview.actions
    )
    assert not accepted.conflicts


def test_accepting_one_legacy_path_does_not_waive_another_edit(tmp_path: Path) -> None:
    """Scoped legacy acceptance does not bypass another changed managed file."""
    project_dir = _legacy_minimal_project(tmp_path)
    agents_path = project_dir / "AGENTS.md"
    git_rules_path = project_dir / ".codex/rules/git.rules"
    agents_path.write_text(
        agents_path.read_text(encoding="utf-8").replace(
            "# Agent Instructions",
            "# Local Agent Instructions",
        ),
        encoding="utf-8",
    )
    git_rules_path.write_text(
        git_rules_path.read_text(encoding="utf-8").replace("prefix_rule(", "# local\nprefix_rule("),
        encoding="utf-8",
    )

    plan = plan_upgrade(project_dir, accept_legacy=(Path("AGENTS.md"),))

    assert plan.conflicts


@pytest.mark.parametrize("case", ["config-only", "partial"])
def test_manifestless_project_without_complete_baseline_is_conflict_only(
    tmp_path: Path,
    case: str,
) -> None:
    """Unknown or incomplete manifest-less projects never plan adoption writes."""
    project_dir = _legacy_minimal_project(tmp_path / case)
    if case == "config-only":
        _remove_legacy_managed_files(project_dir)
    else:
        (project_dir / "AGENTS.md").unlink()

    plan = plan_upgrade(project_dir)
    managed_actions = [action for action in plan.actions if action.lifecycle == "managed"]

    assert plan.conflicts
    assert plan.writes == ()
    assert managed_actions
    assert all(action.kind == "conflict" for action in managed_actions)
    assert not (project_dir / MANIFEST_RELATIVE_PATH).exists()


def test_apply_rolls_back_pyproject_when_existing_lock_refresh_fails(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing uv.lock is snapshotted and restored when post-write lock fails."""
    project_dir = generated_project(tmp_path)
    pyproject_path = project_dir / "pyproject.toml"
    original_pyproject = pyproject_path.read_text(encoding="utf-8")
    legacy_pyproject = original_pyproject.replace("scaffold-guard>=0.2.0", "scaffold-guard>=0.1.3")
    pyproject_path.write_text(legacy_pyproject, encoding="utf-8")
    lock_path = project_dir / "uv.lock"
    lock_path.write_text("old lock\n", encoding="utf-8")

    def fail_lock(root: Path) -> None:
        assert root == project_dir
        lock_path.write_text("new lock\n", encoding="utf-8")
        raise UpgradeError("lock failed")

    monkeypatch.setattr(upgrade_module, "_run_uv_lock", fail_lock)
    plan = plan_upgrade(project_dir)

    assert plan.lock_after_apply
    with pytest.raises(UpgradeError, match="lock failed"):
        apply_upgrade_plan(plan)
    assert pyproject_path.read_text(encoding="utf-8") == legacy_pyproject
    assert lock_path.read_text(encoding="utf-8") == "old lock\n"


def test_upgrade_does_not_lock_when_lockfile_was_absent(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pyproject migration does not create uv.lock from scratch."""
    project_dir = generated_project(tmp_path)
    pyproject_path = project_dir / "pyproject.toml"
    legacy_pyproject = pyproject_path.read_text(encoding="utf-8").replace(
        "scaffold-guard>=0.2.0",
        "scaffold-guard>=0.1.3",
    )
    pyproject_path.write_text(legacy_pyproject, encoding="utf-8")

    def fail_if_called(root: Path) -> None:
        raise AssertionError(f"uv lock should not run for {root}")

    monkeypatch.setattr(upgrade_module, "_run_uv_lock", fail_if_called)
    plan = plan_upgrade(project_dir)

    assert not plan.lock_after_apply


def test_upgrade_detects_crlf_byte_drift_in_managed_file(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Managed-file drift is byte-exact and does not normalize CRLF newlines."""
    project_dir = generated_project(tmp_path)
    agents_path = project_dir / "AGENTS.md"
    agents_path.write_bytes(agents_path.read_bytes().replace(b"\n", b"\r\n"))

    plan = plan_upgrade(project_dir)

    assert any(
        action.kind == "conflict" and action.path == Path("AGENTS.md") and "bytes" in action.reason
        for action in plan.actions
    )


def test_compile_scope_uses_exact_configured_adapters(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Omitted compile-rules agent selection does not expand to unconfigured adapters."""
    project_dir = generated_project(tmp_path, agent="all")
    config_path = project_dir / "scaffold-guard.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        .replace("codex = false", "codex = true")
        .replace("claude = true", "claude = false")
        .replace("cursor = true", "cursor = true"),
        encoding="utf-8",
    )
    config = load_generated_project_config(project_dir)

    files = selected_agent_files(config)

    assert Path(".cursor/rules/python.mdc") in files
    assert Path(".codex/config.toml") in files
    assert Path("CLAUDE.md") not in files
    assert Path(".claude/rules/testing.md") not in files


def test_upgrade_managed_plan_respects_gitlab_and_disabled_tools(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Managed desired files follow CI and optional tool configuration variants."""
    project_dir = generated_project(
        tmp_path,
        profile="typescript",
        ci="gitlab",
        biome=False,
        vitest=False,
    )

    plan = plan_upgrade(project_dir)
    planned_paths = {action.path for action in plan.actions}

    assert Path(".gitlab-ci.yml") in planned_paths
    assert Path(".github/workflows/ci.yml") not in planned_paths
    assert Path("biome.json") not in planned_paths
    assert Path("vitest.config.ts") not in planned_paths


def test_legacy_transaction_orders_structured_then_managed_then_manifest(
    tmp_path: Path,
) -> None:
    """Legacy writes obey transaction ordering while actions obey the public kind order."""
    project_dir = _legacy_minimal_project(tmp_path)

    plan = plan_upgrade(project_dir)
    write_paths = [write.path for write in plan.writes]
    structured_indexes = [
        index
        for index, path in enumerate(write_paths)
        if path in {Path("scaffold-guard.toml"), Path("pyproject.toml")}
    ]
    managed_indexes = [
        index
        for index, path in enumerate(write_paths)
        if path
        not in {
            Path("scaffold-guard.toml"),
            Path("pyproject.toml"),
            Path(MANIFEST_RELATIVE_PATH),
        }
    ]

    assert structured_indexes
    assert managed_indexes
    assert max(structured_indexes) < min(managed_indexes)
    assert write_paths[-1] == Path(MANIFEST_RELATIVE_PATH)
    kinds = [action.kind for action in plan.actions]
    assert kinds == sorted(kinds, key=ACTION_ORDER.index)


def test_upgrade_reports_manifest_actions_for_legacy_noop_and_canonicalization(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """The manifest is visible as add, unchanged, or migrate in planner actions."""
    legacy_plan = plan_upgrade(_legacy_minimal_project(tmp_path / "legacy"))
    project_dir = generated_project(tmp_path / "current")
    noop_plan = plan_upgrade(project_dir)
    manifest_path = project_dir / MANIFEST_RELATIVE_PATH
    manifest_path.write_bytes(b" " + manifest_path.read_bytes())
    canonical_plan = plan_upgrade(project_dir)

    assert _action_for(legacy_plan, MANIFEST_RELATIVE_PATH).kind == "add"
    assert _action_for(noop_plan, MANIFEST_RELATIVE_PATH).kind == "unchanged"
    assert _action_for(canonical_plan, MANIFEST_RELATIVE_PATH).kind == "migrate"
    assert canonical_plan.writes[-1].path == Path(MANIFEST_RELATIVE_PATH)


def test_upgrade_allows_adapter_selection_change_and_preserves_orphan(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Upgrade repairs adapter metadata while retaining deselected managed files."""
    project_dir = generated_project(tmp_path)
    config_path = project_dir / "scaffold-guard.toml"
    _replace_text(config_path, "claude = true", "claude = false")
    claude_path = project_dir / "CLAUDE.md"
    claude_before = claude_path.read_bytes()

    plan = plan_upgrade(project_dir)

    assert _action_for(plan, "CLAUDE.md").kind == "orphan"
    assert _action_for(plan, MANIFEST_RELATIVE_PATH).kind == "update"
    verification = apply_upgrade_plan(plan)
    manifest = load_manifest(project_dir / MANIFEST_RELATIVE_PATH)
    assert verification.ok
    assert claude_path.read_bytes() == claude_before
    assert manifest.adapters == ("codex", "cursor")
    assert any(file.path == "CLAUDE.md" for file in manifest.files)


def test_upgrade_adapter_selection_add_and_collision(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """New configured adapters add absent files but conflict with untracked collisions."""
    add_project = generated_project(tmp_path / "add", agent="codex")
    _replace_text(
        add_project / "scaffold-guard.toml",
        "claude = false",
        "claude = true",
    )

    add_plan = plan_upgrade(add_project)

    assert _action_for(add_plan, "CLAUDE.md").kind == "add"

    collision_project = generated_project(tmp_path / "collision", agent="codex")
    _replace_text(
        collision_project / "scaffold-guard.toml",
        "claude = false",
        "claude = true",
    )
    (collision_project / "CLAUDE.md").write_text("# Local rules\n", encoding="utf-8")

    collision_plan = plan_upgrade(collision_project)

    assert _action_for(collision_plan, "CLAUDE.md").kind == "conflict"


def test_upgrade_selected_managed_missing_and_symlink_are_conflicts(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Tracked managed paths must remain present regular files at planning time."""
    missing_project = generated_project(tmp_path / "missing")
    (missing_project / ".claude/rules/testing.md").unlink()
    missing_plan = plan_upgrade(missing_project)

    symlink_project = generated_project(tmp_path / "symlink")
    external = tmp_path / "external-agents.md"
    external.write_text("# External\n", encoding="utf-8")
    agents_path = symlink_project / "AGENTS.md"
    agents_path.unlink()
    agents_path.symlink_to(external)
    symlink_plan = plan_upgrade(symlink_project)

    assert _action_for(missing_plan, ".claude/rules/testing.md").kind == "conflict"
    assert _action_for(symlink_plan, "AGENTS.md").kind == "conflict"


def test_upgrade_new_managed_path_rejects_symlink_component(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """A newly selected adapter cannot write through a symlinked path family."""
    project_dir = generated_project(tmp_path / "project", agent="codex")
    _replace_text(project_dir / "scaffold-guard.toml", "claude = false", "claude = true")
    internal = project_dir / "local-claude"
    internal.mkdir()
    (project_dir / ".claude").symlink_to(internal, target_is_directory=True)

    plan = plan_upgrade(project_dir)

    assert any(
        action.kind == "conflict" and action.path.as_posix().startswith(".claude/")
        for action in plan.actions
    )


def test_legacy_exact_match_rejects_crlf_and_extra_recognized_paths(tmp_path: Path) -> None:
    """Legacy adoption compares exact bytes and requires the full recognized path set."""
    crlf_project = _legacy_minimal_project(tmp_path / "crlf")
    agents_path = crlf_project / "AGENTS.md"
    agents_path.write_bytes(agents_path.read_bytes().replace(b"\n", b"\r\n"))

    assert plan_upgrade(crlf_project).conflicts

    extra_project = _legacy_minimal_project(tmp_path / "extra")
    (extra_project / "CLAUDE.md").write_bytes((extra_project / "AGENTS.md").read_bytes())

    assert plan_upgrade(extra_project).conflicts
    with pytest.raises(UpgradeError, match="complete supported legacy file set"):
        plan_upgrade(extra_project, accept_legacy=(Path("AGENTS.md"),))


def test_accept_legacy_unsafe_paths_are_conflict_actions(tmp_path: Path) -> None:
    """Accepted path escape and symlink components fail in preview with conflicts."""
    escaped_project = _legacy_minimal_project(tmp_path / "escaped")
    escaped_plan = plan_upgrade(
        escaped_project,
        accept_legacy=(Path("../AGENTS.md"),),
    )
    assert escaped_plan.conflicts
    assert _action_for(escaped_plan, "../AGENTS.md").kind == "conflict"

    symlink_project = _legacy_minimal_project(tmp_path / "symlink")
    rules_path = symlink_project / ".codex/rules"
    external_rules = tmp_path / "external-rules"
    rules_path.rename(external_rules)
    rules_path.symlink_to(external_rules, target_is_directory=True)
    symlink_plan = plan_upgrade(
        symlink_project,
        accept_legacy=(Path(".codex/rules/git.rules"),),
    )

    assert _action_for(symlink_plan, ".codex/rules/git.rules").kind == "conflict"


def test_legacy_managed_nonregular_targets_are_conflicts(tmp_path: Path) -> None:
    """Exact and accepted legacy planning reject managed directories and symlink files."""
    directory_project = _legacy_minimal_project(tmp_path / "directory")
    directory_agents = directory_project / "AGENTS.md"
    directory_agents.unlink()
    directory_agents.mkdir()
    directory_plan = plan_upgrade(directory_project)
    accepted_directory_plan = plan_upgrade(
        directory_project,
        accept_legacy=(Path("AGENTS.md"),),
    )

    symlink_project = _legacy_minimal_project(tmp_path / "symlink-file")
    symlink_agents = symlink_project / "AGENTS.md"
    internal = symlink_project / "local-agents.md"
    internal.write_bytes(symlink_agents.read_bytes())
    symlink_agents.unlink()
    symlink_agents.symlink_to(internal)
    symlink_plan = plan_upgrade(symlink_project)

    assert _action_for(directory_plan, "AGENTS.md").kind == "conflict"
    assert _action_for(accepted_directory_plan, "AGENTS.md").kind == "conflict"
    assert _action_for(symlink_plan, "AGENTS.md").kind == "conflict"


@pytest.mark.parametrize("target_kind", ["directory", "symlink"])
def test_legacy_structured_target_preflight_returns_conflict(
    tmp_path: Path,
    target_kind: str,
) -> None:
    """Unsafe legacy pyproject targets become conflict actions before migration parsing."""
    project_dir = _legacy_minimal_project(tmp_path / target_kind)
    pyproject_path = project_dir / "pyproject.toml"
    if target_kind == "directory":
        pyproject_path.mkdir()
    else:
        external = tmp_path / "external-pyproject.toml"
        external.write_text("not valid toml", encoding="utf-8")
        pyproject_path.symlink_to(external)

    plan = plan_upgrade(project_dir)

    assert _action_for(plan, "pyproject.toml").kind == "conflict"


@pytest.mark.parametrize("profile", ["minimal", "typescript"])
def test_v02_missing_pyproject_is_not_recreated_by_legacy_exception(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    profile: str,
) -> None:
    """Only manifest-less legacy minimal and TypeScript projects may create pyproject."""
    project_dir = generated_project(tmp_path / profile, profile=profile)
    (project_dir / "pyproject.toml").unlink()

    with pytest.raises(UpgradeError, match="unexpectedly missing"):
        plan_upgrade(project_dir)


def test_upgrade_rejects_symlinked_manifest_parent(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """A symlinked .scaffold-guard parent cannot be loaded or treated as legacy."""
    project_dir = generated_project(tmp_path / "project")
    manifest_dir = project_dir / ".scaffold-guard"
    external_manifest_dir = tmp_path / "external-manifest"
    manifest_dir.rename(external_manifest_dir)
    manifest_dir.symlink_to(external_manifest_dir, target_is_directory=True)

    with pytest.raises(UpgradeError, match="symbolic-link component"):
        plan_upgrade(project_dir)


def test_apply_rolls_back_all_upgrade_outputs_when_verification_fails(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verification failure restores structured, managed, manifest, and lock bytes."""
    project_dir = generated_project(tmp_path)
    config_path = project_dir / "scaffold-guard.toml"
    config_text = config_path.read_text(encoding="utf-8")
    config_path.write_text(
        config_text.replace('generated_with = "0.2.0"', 'generated_with = "0.1.5"')
        .replace('requires_scaffold_guard = ">=0.2.0"', 'requires_scaffold_guard = ">=0.1.3"')
        .replace("ruff = true", "ruff = false")
        .replace('ruff_mode = "strict"', 'ruff_mode = "off"'),
        encoding="utf-8",
    )
    pyproject_path = project_dir / "pyproject.toml"
    _replace_text(pyproject_path, "scaffold-guard>=0.2.0", "scaffold-guard>=0.1.3")
    manifest_path = project_dir / MANIFEST_RELATIVE_PATH
    manifest = load_manifest(manifest_path)
    write_manifest(
        manifest_path,
        replace(
            manifest,
            generated_with="0.1.5",
            requires_scaffold_guard=">=0.1.3",
        ),
    )
    lock_path = project_dir / "uv.lock"
    lock_path.write_text("old lock\n", encoding="utf-8")
    tracked_paths = (
        config_path,
        pyproject_path,
        project_dir / "AGENTS.md",
        manifest_path,
        lock_path,
    )
    before = {path: path.read_bytes() for path in tracked_paths}

    def update_lock(root: Path) -> None:
        assert root == project_dir
        lock_path.write_text("new lock\n", encoding="utf-8")

    def fail_verification(root: Path) -> CheckReport:
        assert root == project_dir
        return CheckReport(
            path=root,
            checks=(
                CheckResult(
                    id="forced-failure",
                    findings=(
                        finding(
                            "AGENTS.md",
                            line=0,
                            code="forced-failure",
                            message="verification failed",
                        ),
                    ),
                ),
            ),
        )

    monkeypatch.setattr(upgrade_module, "_run_uv_lock", update_lock)
    monkeypatch.setattr(upgrade_module, "_targeted_verification", fail_verification)
    plan = plan_upgrade(project_dir)

    assert plan.lock_after_apply
    assert {write.path for write in plan.writes}.issuperset(
        {
            Path("scaffold-guard.toml"),
            Path("pyproject.toml"),
            Path("AGENTS.md"),
            Path(MANIFEST_RELATIVE_PATH),
        }
    )
    with pytest.raises(UpgradeError, match="Post-apply verification failed"):
        apply_upgrade_plan(plan)
    assert {path: path.read_bytes() for path in tracked_paths} == before


def test_apply_runs_targeted_verification_once_inside_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful write transaction returns its single in-transaction verification."""
    project_dir = _legacy_minimal_project(tmp_path)
    plan = plan_upgrade(project_dir)
    expected = CheckReport(path=project_dir, checks=())
    calls: list[Path] = []

    def verify(root: Path) -> CheckReport:
        calls.append(root)
        return expected

    monkeypatch.setattr(upgrade_module, "_targeted_verification", verify)

    result = apply_upgrade_plan(plan)

    assert result is expected
    assert calls == [project_dir]


def test_apply_refuses_conflicted_plan_and_result_reports_verification_failure(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Conflicts cannot apply, while failed verification maps to public exit code two."""
    project_dir = generated_project(tmp_path)
    (project_dir / "AGENTS.md").write_text("# Local\n", encoding="utf-8")
    conflicted = plan_upgrade(project_dir)

    with pytest.raises(UpgradeError, match="plan with conflicts"):
        apply_upgrade_plan(conflicted)

    clean_project = generated_project(tmp_path / "clean")
    clean_plan = plan_upgrade(clean_project)
    failed_report = CheckReport(
        path=clean_project,
        checks=(
            CheckResult(
                id="failed",
                findings=(finding("AGENTS.md", line=0, code="failed", message="failed"),),
            ),
        ),
    )
    result = UpgradeResult(
        plan=clean_plan,
        applied=True,
        post_apply_verification=failed_report,
    )

    assert not result.ok
    assert result.exit_code == CONFIG_ERROR
    assert result.to_json()["post_apply_verification"] == failed_report.to_json()


def test_upgrade_force_reconciles_tracked_drift_and_untracked_collision(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Force replaces reviewed tracked drift and untracked selected adapter files."""
    tracked_project = generated_project(tmp_path / "tracked")
    agents_path = tracked_project / "AGENTS.md"
    expected_agents = agents_path.read_bytes()
    agents_path.write_text("# Local\n", encoding="utf-8")

    tracked_plan = plan_upgrade(tracked_project, force=True)

    assert not tracked_plan.conflicts
    assert _action_for(tracked_plan, "AGENTS.md").kind == "update"
    apply_upgrade_plan(tracked_plan)
    assert agents_path.read_bytes() == expected_agents

    collision_project = generated_project(tmp_path / "collision", agent="codex")
    _replace_text(
        collision_project / "scaffold-guard.toml",
        "claude = false",
        "claude = true",
    )
    claude_path = collision_project / "CLAUDE.md"
    claude_path.write_text("# Local\n", encoding="utf-8")

    collision_plan = plan_upgrade(collision_project, force=True)

    assert not collision_plan.conflicts
    assert _action_for(collision_plan, "CLAUDE.md").kind == "add"
    apply_upgrade_plan(collision_plan)
    assert b"generated by scaffold-guard" in claude_path.read_bytes()


def test_upgrade_force_still_rejects_untracked_symlink(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Force never expands to writing a newly selected destination through a symlink."""
    project_dir = generated_project(tmp_path / "project", agent="codex")
    _replace_text(project_dir / "scaffold-guard.toml", "claude = false", "claude = true")
    internal = project_dir / "local-claude.md"
    internal.write_text("# Local\n", encoding="utf-8")
    (project_dir / "CLAUDE.md").symlink_to(internal)

    plan = plan_upgrade(project_dir, force=True)

    assert _action_for(plan, "CLAUDE.md").kind == "conflict"


def test_upgrade_rejects_accept_legacy_on_manifest_project(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Legacy acceptance is invalid when a managed-file manifest already exists."""
    project_dir = generated_project(tmp_path)

    with pytest.raises(UpgradeError, match="manifest-less legacy"):
        plan_upgrade(project_dir, accept_legacy=(Path("AGENTS.md"),))


def test_accept_legacy_argument_validation_errors(tmp_path: Path) -> None:
    """Accepted legacy paths must be recognized, present, marker-bearing UTF-8 files."""
    unknown_project = _legacy_minimal_project(tmp_path / "unknown")
    with pytest.raises(UpgradeError, match="not recognized"):
        plan_upgrade(unknown_project, accept_legacy=(Path("unknown.md"),))

    missing_project = _legacy_minimal_project(tmp_path / "missing")
    with pytest.raises(UpgradeError, match="missing or not a regular file"):
        plan_upgrade(missing_project, accept_legacy=(Path("CLAUDE.md"),))

    unmarked_project = _legacy_minimal_project(tmp_path / "unmarked")
    agents_path = unmarked_project / "AGENTS.md"
    agents_path.write_text(
        agents_path.read_text(encoding="utf-8").replace(
            "generated by scaffold-guard",
            "locally maintained",
        ),
        encoding="utf-8",
    )
    with pytest.raises(UpgradeError, match="not marker-bearing"):
        plan_upgrade(unmarked_project, accept_legacy=(Path("AGENTS.md"),))

    invalid_utf8_project = _legacy_minimal_project(tmp_path / "invalid-utf8")
    invalid_agents = invalid_utf8_project / "AGENTS.md"
    invalid_agents.write_bytes(invalid_agents.read_bytes() + b"\xff")
    with pytest.raises(UpgradeError, match="Unable to read UTF-8"):
        plan_upgrade(invalid_utf8_project, accept_legacy=(Path("AGENTS.md"),))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("generated_with", "0.1.5", "generated_with"),
        ("requires_scaffold_guard", ">=0.1.3", "requires_scaffold_guard"),
    ],
)
def test_upgrade_rejects_strict_manifest_metadata_mismatch(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    field: str,
    value: str,
    message: str,
) -> None:
    """Generated-with and runtime requirement mismatches remain strict planner errors."""
    project_dir = generated_project(tmp_path)
    manifest_path = project_dir / MANIFEST_RELATIVE_PATH
    manifest = load_manifest(manifest_path)
    updated = (
        replace(manifest, generated_with=value)
        if field == "generated_with"
        else replace(manifest, requires_scaffold_guard=value)
    )
    write_manifest(manifest_path, updated)

    with pytest.raises(UpgradeError, match=message):
        plan_upgrade(project_dir)


def test_uv_lock_errors_are_normalized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing uv and lock subprocess failures become upgrade errors."""
    run_uv_lock = cast("Callable[[Path], None]", upgrade_module.__dict__["_run_uv_lock"])

    def missing_uv(name: str) -> None:
        assert name == "uv"

    monkeypatch.setattr("scaffold_guard.upgrade.shutil.which", missing_uv)
    with pytest.raises(UpgradeError, match="uv was not found"):
        run_uv_lock(tmp_path)

    def available_true(name: str) -> str:
        assert name == "uv"
        return "/usr/bin/true"

    monkeypatch.setattr("scaffold_guard.upgrade.shutil.which", available_true)
    run_uv_lock(tmp_path)

    async def failed_lock(uv_path: str, root: Path) -> tuple[int, str, str]:
        assert uv_path == "/usr/bin/uv"
        assert root == tmp_path
        return 1, "", "lock failed"

    def available_uv(name: str) -> str:
        assert name == "uv"
        return "/usr/bin/uv"

    monkeypatch.setattr("scaffold_guard.upgrade.shutil.which", available_uv)
    monkeypatch.setattr(upgrade_module, "_run_uv_lock_process", failed_lock)
    with pytest.raises(UpgradeError, match="lock failed"):
        run_uv_lock(tmp_path)


def test_structured_planner_helpers_cover_transitional_safety_branches(tmp_path: Path) -> None:
    """Structured planners reject unsafe transitional records and preserve exact no-ops."""
    plan_migration = cast(
        "_MigrationPlanner",
        upgrade_module.__dict__["_plan_migration"],
    )
    plan_legacy_migration = cast(
        "_LegacyMigrationPlanner",
        upgrade_module.__dict__["_plan_legacy_migration"],
    )
    migration = StructuredFileChange(
        path=Path("config.toml"),
        kind="migrate",
        description="Update config.",
        content="value = 2\n",
    )

    internal = tmp_path / "internal"
    internal.mkdir()
    (tmp_path / "linked").symlink_to(internal, target_is_directory=True)
    linked_action, _ = plan_migration(
        tmp_path,
        Path("linked/config.toml"),
        None,
        replace(migration, path=Path("linked/config.toml")),
    )
    assert linked_action.kind == "conflict"

    missing_record = ManifestFile(
        path="missing.toml",
        template_id="legacy/missing",
        sha256=bytes_sha256(b"baseline\n"),
    )
    missing_action, _ = plan_migration(
        tmp_path,
        Path("missing.toml"),
        missing_record,
        replace(migration, path=Path("missing.toml")),
    )
    assert missing_action.kind == "conflict"

    drift_path = tmp_path / "drift.toml"
    drift_path.write_text("actual = true\n", encoding="utf-8")
    drift_record = replace(missing_record, path="drift.toml")
    drift_action, _ = plan_migration(
        tmp_path,
        Path("drift.toml"),
        drift_record,
        replace(migration, path=Path("drift.toml")),
    )
    assert drift_action.kind == "conflict"

    directory_path = tmp_path / "directory.toml"
    directory_path.mkdir()
    directory_action, _ = plan_migration(
        tmp_path,
        Path("directory.toml"),
        None,
        replace(migration, path=Path("directory.toml")),
    )
    assert directory_action.kind == "conflict"

    unchanged_path = tmp_path / "unchanged.toml"
    unchanged_path.write_text(migration.content, encoding="utf-8")
    unchanged_action, unchanged_write = plan_migration(
        tmp_path,
        Path("unchanged.toml"),
        None,
        replace(migration, path=Path("unchanged.toml")),
    )
    assert unchanged_action.kind == "unchanged"
    assert unchanged_write is None

    legacy_linked, _ = plan_legacy_migration(
        tmp_path,
        path=Path("linked/config.toml"),
        migration=replace(migration, path=Path("linked/config.toml")),
    )
    legacy_directory, _ = plan_legacy_migration(
        tmp_path,
        path=Path("directory.toml"),
        migration=replace(migration, path=Path("directory.toml")),
    )
    legacy_unchanged, _ = plan_legacy_migration(
        tmp_path,
        path=Path("unchanged.toml"),
        migration=replace(migration, path=Path("unchanged.toml")),
    )
    assert legacy_linked.kind == "conflict"
    assert legacy_directory.kind == "conflict"
    assert legacy_unchanged.kind == "unchanged"


def test_internal_legacy_and_metadata_guards_normalize_defensive_failures(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Defensive legacy marker, read, and project-format branches remain explicit."""
    accepted_planner = cast(
        "_AcceptedLegacyPlanner",
        upgrade_module.__dict__["_plan_accepted_legacy_file"],
    )
    current = tmp_path / "accepted.md"
    current.write_text("# Local\n", encoding="utf-8")
    rendered = RenderedFile(path=Path("accepted.md"), content="# Generated\n")
    accepted_action, _ = accepted_planner(
        current,
        file=rendered,
        accepted={Path("accepted.md")},
    )
    assert accepted_action.kind == "conflict"

    read_bytes = cast(
        "Callable[[Path], bytes]",
        upgrade_module.__dict__["_read_bytes"],
    )
    unreadable = tmp_path / "unreadable"
    unreadable.mkdir()
    with pytest.raises(UpgradeError, match="Unable to read generated file"):
        read_bytes(unreadable)

    project_dir = generated_project(tmp_path / "metadata")
    config = load_generated_project_config(project_dir)
    manifest = load_manifest(project_dir / MANIFEST_RELATIVE_PATH)
    validate_metadata = cast(
        "_ManifestMetadataValidator",
        upgrade_module.__dict__["_validate_manifest_metadata"],
    )
    with pytest.raises(UpgradeError, match="project format"):
        validate_metadata(config, replace(manifest, project_format_version=2))


def test_upgrade_text_cli_reports_preview_apply_conflict_and_error(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Human CLI output covers successful preview/apply plus conflict and invalid paths."""
    preview_project = generated_project(tmp_path / "preview")
    preview = CliRunner().invoke(app, ["upgrade", "--path", str(preview_project)])
    assert preview.exit_code == 0, preview.output
    assert "Planned ScaffoldGuard upgrade" in preview.output
    assert "Actions:" in preview.output

    apply_project = _legacy_minimal_project(tmp_path / "apply")
    applied = CliRunner().invoke(
        app,
        ["upgrade", "--path", str(apply_project), "--apply"],
    )
    assert applied.exit_code == 0, applied.output
    assert "Applied ScaffoldGuard upgrade" in applied.output
    assert "post-apply verification: ok" in applied.output

    conflict_project = generated_project(tmp_path / "conflict")
    (conflict_project / "AGENTS.md").write_text("# Local\n", encoding="utf-8")
    conflict = CliRunner().invoke(app, ["upgrade", "--path", str(conflict_project)])
    assert conflict.exit_code == 1
    assert "conflict: AGENTS.md" in conflict.output

    invalid = CliRunner().invoke(app, ["upgrade", "--path", str(tmp_path / "missing")])
    assert invalid.exit_code == CONFIG_ERROR
    assert "Error:" in invalid.output


def _action_for(plan: UpgradePlan, path: str) -> UpgradeAction:
    """Return the single planned action for a path."""
    return next(action for action in plan.actions if action.path == Path(path))


def _replace_text(path: Path, old: str, new: str) -> None:
    """Replace exact UTF-8 text in a fixture file."""
    path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")


def _remove_legacy_managed_files(project_dir: Path) -> None:
    """Leave only the legacy config in a manifest-less project fixture."""
    for path in project_dir.rglob("*"):
        if path.is_file() and path.name != "scaffold-guard.toml":
            path.unlink()


def _legacy_minimal_project(tmp_path: Path) -> Path:
    """Create a manifest-less project from an exact historical managed baseline."""
    project_dir = tmp_path / "demo"
    project_dir.mkdir(parents=True)
    (project_dir / "scaffold-guard.toml").write_text(
        "\n".join(
            (
                "[project]",
                'name = "demo"',
                'package = "demo"',
                'profile = "minimal"',
                'python_min = "3.13"',
                "coverage_fail_under = 95",
                'ci = "github"',
                "",
                "[agents]",
                "codex = true",
                "claude = false",
                "cursor = false",
                "",
                "[features]",
                "docs = false",
                "github_actions = true",
                "gitlab_ci = false",
                "",
                "[tools]",
                "ruff = false",
                "mypy = false",
                "pyright = false",
                "typescript_strict = false",
                "biome = false",
                "vitest = false",
                "",
            )
        ),
        encoding="utf-8",
    )
    options = build_init_options(
        "demo",
        base_dir=tmp_path,
        agent="codex",
        profile="minimal",
        license_name="MIT",
        python_min="3.13",
        coverage=95,
        ci="github",
        dry_run=True,
        force=False,
    )
    legacy_config = LegacyCatalogConfig(
        profile="minimal",
        adapters=("codex",),
        ci="github",
        render_context=build_render_context(options),
    )
    for file in render_legacy_managed_files(legacy_config, release="v0.1.5"):
        target = project_dir / file.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(file.content, encoding="utf-8")
    return project_dir
