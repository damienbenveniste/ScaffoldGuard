"""Generated-project upgrade planning and transactional reconciliation."""

import asyncio
import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from scaffold_guard import __version__
from scaffold_guard.checks.base import CheckReport
from scaffold_guard.checks.config_consistency import check_config_consistency
from scaffold_guard.checks.generated_files import check_generated_files
from scaffold_guard.checks.project_health import check_project_health
from scaffold_guard.fs import (
    TransactionalWrite,
    apply_file_transaction,
    ensure_relative_safe_path,
    has_symlink_component,
    is_within_directory,
)
from scaffold_guard.legacy import (
    LEGACY_RELEASES,
    LegacyCatalogConfig,
    LegacyRelease,
    legacy_managed_paths,
    render_legacy_managed_files,
)
from scaffold_guard.manifest import (
    MANIFEST_RELATIVE_PATH,
    ManifestFile,
    ProjectManifest,
    bytes_sha256,
    content_sha256,
    load_manifest,
    manifest_json,
)
from scaffold_guard.migrations import (
    MigrationError,
    StructuredFileChange,
    plan_dependency_floor_migration,
    plan_project_metadata_migration,
)
from scaffold_guard.models import (
    AdapterSelection,
    CiChoice,
    InitOptions,
    ProfileChoice,
    TemplateLifecycle,
)
from scaffold_guard.project_config import GeneratedProjectConfig, load_generated_project_config
from scaffold_guard.scaffold import (
    RenderedFile,
    build_project_manifest,
    build_render_context,
    render_package_files,
)
from scaffold_guard.versions import (
    GENERATED_PROJECT_MINIMUM_VERSION,
    MANIFEST_VERSION,
    PROJECT_FORMAT_VERSION,
)

UpgradeActionKind = Literal["unchanged", "add", "update", "migrate", "conflict", "orphan"]
UpgradeFailureKind = Literal["conflict", "invalid"]

ACTION_ORDER: tuple[UpgradeActionKind, ...] = (
    "unchanged",
    "add",
    "update",
    "migrate",
    "conflict",
    "orphan",
)
STRUCTURED_MIGRATION_PATHS: frozenset[Path] = frozenset(
    (Path("scaffold-guard.toml"), Path("pyproject.toml"))
)


class UpgradeError(RuntimeError):
    """Raised when an upgrade cannot be planned or applied."""

    def __init__(self, message: str, *, kind: UpgradeFailureKind = "invalid") -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True, slots=True)
class UpgradeAction:
    """One ordered upgrade planner action."""

    kind: UpgradeActionKind
    path: Path
    lifecycle: TemplateLifecycle | None
    reason: str

    def to_json(self) -> dict[str, object]:
        """Return a JSON-serializable action payload."""
        return {
            "kind": self.kind,
            "path": self.path.as_posix(),
            "lifecycle": self.lifecycle,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class UpgradeMetadata:
    """Project metadata included in upgrade output."""

    manifest_version: int | None
    project_format_version: int | None
    profile: str
    adapters: tuple[AdapterSelection, ...]
    generated_with: str | None = None
    requires_scaffold_guard: str | None = None
    legacy_release: str | None = None

    def to_json(self) -> dict[str, object]:
        """Return a JSON-serializable metadata payload."""
        return {
            "manifest_version": self.manifest_version,
            "project_format_version": self.project_format_version,
            "profile": self.profile,
            "adapters": list(self.adapters),
            "generated_with": self.generated_with,
            "requires_scaffold_guard": self.requires_scaffold_guard,
            "legacy_release": self.legacy_release,
        }


@dataclass(frozen=True, slots=True)
class _LegacyPlanMatch:
    """Legacy release candidate selected for planning."""

    release: LegacyRelease
    managed_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UpgradePlan:
    """Read-only generated-project upgrade plan."""

    path: Path
    current: UpgradeMetadata
    target: UpgradeMetadata
    actions: tuple[UpgradeAction, ...]
    writes: tuple[TransactionalWrite, ...]
    lock_after_apply: bool

    @property
    def conflicts(self) -> tuple[UpgradeAction, ...]:
        """Return conflict actions in the plan."""
        return tuple(action for action in self.actions if action.kind == "conflict")

    @property
    def ok(self) -> bool:
        """Return whether the plan has no conflicts."""
        return not self.conflicts

    def to_json(self) -> dict[str, object]:
        """Return a JSON-serializable plan payload."""
        return {
            "ok": self.ok,
            "path": str(self.path),
            "applied": False,
            "current": self.current.to_json(),
            "target": self.target.to_json(),
            "actions": [action.to_json() for action in self.actions],
            "conflicts": [action.to_json() for action in self.conflicts],
            "post_apply_verification": None,
        }


@dataclass(frozen=True, slots=True)
class UpgradeResult:
    """Upgrade preview or apply result."""

    plan: UpgradePlan
    applied: bool
    post_apply_verification: CheckReport | None

    @property
    def ok(self) -> bool:
        """Return whether the preview or apply succeeded without conflicts."""
        return self.plan.ok and (
            self.post_apply_verification is None or self.post_apply_verification.ok
        )

    @property
    def exit_code(self) -> int:
        """Return the public CLI exit code for this result."""
        if self.plan.conflicts:
            return 1
        if not self.ok:
            return 2
        return 0

    def to_json(self) -> dict[str, object]:
        """Return a JSON-serializable result payload."""
        payload = self.plan.to_json()
        payload["ok"] = self.ok
        payload["applied"] = self.applied
        payload["post_apply_verification"] = (
            None if self.post_apply_verification is None else self.post_apply_verification.to_json()
        )
        return payload


def plan_upgrade(
    root: Path,
    *,
    accept_legacy: tuple[Path, ...] = (),
    paths: tuple[Path, ...] | None = None,
    force: bool = False,
    include_migrations: bool = True,
) -> UpgradePlan:
    """Plan a generated-project upgrade without mutating the filesystem."""
    resolved_root = root.resolve(strict=False)
    config = load_generated_project_config(resolved_root)
    options = _config_init_options(config, dry_run=True, force=True)
    rendered_for_migrations = render_package_files(options)
    rendered_files = _desired_rendered_files(config, paths=paths)
    desired_manifest = replace(
        build_project_manifest(
            options,
            rendered_files,
        ),
        adapters=config.adapters,
    )
    migration_conflicts = (
        _structured_path_preflight_conflicts(config.root) if include_migrations else ()
    )
    migrations = (
        _structured_migrations(config, rendered_for_migrations)
        if include_migrations and not migration_conflicts
        else ()
    )
    manifest_path = resolved_root / MANIFEST_RELATIVE_PATH
    if has_symlink_component(resolved_root, Path(MANIFEST_RELATIVE_PATH)):
        raise UpgradeError("Managed-file manifest path contains a symbolic-link component.")
    if manifest_path.exists():
        if accept_legacy:
            raise UpgradeError("--accept-legacy is only valid for manifest-less legacy projects.")
        current_manifest = load_manifest(manifest_path)
        _validate_manifest_metadata(config, current_manifest)
        return _plan_manifest_project(
            config,
            current_manifest=current_manifest,
            target_manifest=desired_manifest,
            rendered_files=rendered_files,
            migrations=migrations,
            migration_conflicts=migration_conflicts,
            force=force,
            full_scope=paths is None,
        )
    return _plan_legacy_project(
        config,
        target_manifest=desired_manifest,
        rendered_files=rendered_files,
        migrations=migrations,
        migration_conflicts=migration_conflicts,
        accept_legacy=accept_legacy,
        paths=paths,
    )


def run_upgrade(
    root: Path,
    *,
    apply: bool,
    accept_legacy: tuple[Path, ...] = (),
) -> UpgradeResult:
    """Preview or apply a generated-project upgrade."""
    plan = plan_upgrade(root, accept_legacy=accept_legacy)
    if plan.conflicts or not apply:
        return UpgradeResult(plan=plan, applied=False, post_apply_verification=None)
    verification = apply_upgrade_plan(plan)
    return UpgradeResult(plan=plan, applied=True, post_apply_verification=verification)


def apply_upgrade_plan(plan: UpgradePlan) -> CheckReport:
    """Apply an upgrade plan transactionally and run targeted verification."""
    if plan.conflicts:
        raise UpgradeError("Cannot apply an upgrade plan with conflicts.", kind="conflict")
    if not plan.writes:
        return _targeted_verification(plan.path)

    backup_paths = (Path("uv.lock"),) if (plan.path / "uv.lock").exists() else ()
    verification: CheckReport | None = None

    def after_write() -> None:
        nonlocal verification
        if plan.lock_after_apply:
            _run_uv_lock(plan.path)
        verification = _targeted_verification(plan.path)
        if not verification.ok:
            raise UpgradeError("Post-apply verification failed.")

    apply_file_transaction(
        plan.path,
        plan.writes,
        backup_paths=backup_paths,
        after_write=after_write,
    )
    if verification is None:
        raise UpgradeError("Post-apply verification did not run.")
    return verification


def _plan_manifest_project(
    config: GeneratedProjectConfig,
    *,
    current_manifest: ProjectManifest,
    target_manifest: ProjectManifest,
    rendered_files: tuple[RenderedFile, ...],
    migrations: tuple[StructuredFileChange, ...],
    migration_conflicts: tuple[UpgradeAction, ...],
    force: bool,
    full_scope: bool,
) -> UpgradePlan:
    """Plan reconciliation for a manifest-bearing project."""
    desired_by_path = {file.path: file for file in rendered_files}
    target_files = {Path(file.path): file for file in target_manifest.files}
    current_files = {Path(file.path): file for file in current_manifest.files}
    migration_by_path = {change.path: change for change in migrations}
    actions: list[UpgradeAction] = list(migration_conflicts)
    managed_writes: list[TransactionalWrite] = []
    migration_writes: list[TransactionalWrite] = []

    for path in sorted(target_files):
        current_file = current_files.get(path)
        if current_file is None:
            action, write = _plan_add(config.root, desired_by_path[path], force=force)
        else:
            action, write = _plan_tracked_file(
                config.root,
                current_file,
                desired_by_path[path],
                force=force,
            )
        actions.append(action)
        if write is not None:
            managed_writes.append(write)

    for path, migration in sorted(migration_by_path.items()):
        action, write = _plan_migration(config.root, path, current_files.get(path), migration)
        actions.append(action)
        if write is not None:
            migration_writes.append(write)

    if full_scope:
        for path, current_file in sorted(current_files.items()):
            if path not in target_files and current_file.lifecycle == "managed":
                actions.append(
                    UpgradeAction(
                        kind="orphan",
                        path=path,
                        lifecycle=current_file.lifecycle,
                        reason="Previously managed file is no longer selected; left in place.",
                    )
                )

    writes = [*migration_writes, *managed_writes]
    effective_target_manifest = _merge_scoped_manifest(
        current_manifest=current_manifest,
        target_manifest=target_manifest,
        selected_paths=tuple(target_files),
    )
    manifest_action = _existing_manifest_action(
        config.root,
        current=current_manifest,
        target=effective_target_manifest,
    )
    actions.append(manifest_action)
    if (
        not any(action.kind == "conflict" for action in actions)
        and manifest_action.kind != "unchanged"
    ):
        writes.append(_manifest_write(effective_target_manifest))

    return UpgradePlan(
        path=config.root,
        current=_metadata_from_manifest(current_manifest),
        target=_target_metadata(config),
        actions=_ordered_actions(actions),
        writes=tuple(writes),
        lock_after_apply=_needs_lock(config.root, writes),
    )


def _plan_legacy_project(
    config: GeneratedProjectConfig,
    *,
    target_manifest: ProjectManifest,
    rendered_files: tuple[RenderedFile, ...],
    migrations: tuple[StructuredFileChange, ...],
    migration_conflicts: tuple[UpgradeAction, ...],
    accept_legacy: tuple[Path, ...],
    paths: tuple[Path, ...] | None,
) -> UpgradePlan:
    """Plan strict adoption for a manifest-less legacy project."""
    accepted, accept_conflicts = _preflight_accept_legacy_paths(config.root, accept_legacy)
    legacy_config = _legacy_catalog_config(config)
    if accept_conflicts:
        preflight_paths = {action.path for action in accept_conflicts}
        preflight_actions = [
            *migration_conflicts,
            *accept_conflicts,
            *_legacy_baseline_conflicts(rendered_files, excluded=preflight_paths),
        ]
        return UpgradePlan(
            path=config.root,
            current=_legacy_metadata(config, None),
            target=_target_metadata(config),
            actions=_ordered_actions(preflight_actions),
            writes=(),
            lock_after_apply=False,
        )
    _validate_accept_legacy_arguments(config, legacy_config=legacy_config, accepted=accepted)
    legacy_match = _legacy_plan_match(config, legacy_config=legacy_config, accepted=accepted)
    if legacy_match is None:
        conflict_actions = [
            *migration_conflicts,
            *_legacy_baseline_conflicts(rendered_files),
        ]
        return UpgradePlan(
            path=config.root,
            current=_legacy_metadata(config, None),
            target=_target_metadata(config),
            actions=_ordered_actions(conflict_actions),
            writes=(),
            lock_after_apply=False,
        )
    actions: list[UpgradeAction] = list(migration_conflicts)
    migration_writes: list[TransactionalWrite] = []
    managed_writes: list[TransactionalWrite] = []
    rendered_by_path = {file.path: file for file in rendered_files}
    migration_by_path = {change.path: change for change in migrations}
    legacy_paths = set(legacy_match.managed_paths)
    scoped_paths = None if paths is None else {path.as_posix() for path in paths}

    _append_legacy_migrations(
        config.root,
        actions=actions,
        writes=migration_writes,
        migration_by_path=migration_by_path,
        scoped_paths=scoped_paths,
    )

    for file in rendered_files:
        if scoped_paths is not None and file.path.as_posix() not in scoped_paths:
            continue
        action, write = _plan_legacy_file(
            config,
            file=file,
            accepted=accepted,
            legacy_paths=legacy_paths,
        )
        actions.append(action)
        if write is not None:
            managed_writes.append(write)

    _append_legacy_orphans(
        actions=actions,
        legacy_match=legacy_match,
        rendered_by_path=rendered_by_path,
        scoped_paths=scoped_paths,
    )

    manifest_action = _legacy_manifest_action()
    actions.append(manifest_action)
    writes = [*migration_writes, *managed_writes]
    if not any(action.kind == "conflict" for action in actions):
        writes.append(_manifest_write(target_manifest))

    return UpgradePlan(
        path=config.root,
        current=_legacy_metadata(config, legacy_match),
        target=_target_metadata(config),
        actions=_ordered_actions(actions),
        writes=tuple(writes),
        lock_after_apply=_needs_lock(config.root, writes),
    )


def _legacy_baseline_conflicts(
    rendered_files: tuple[RenderedFile, ...],
    *,
    excluded: set[Path] | None = None,
) -> tuple[UpgradeAction, ...]:
    """Return conflict actions when no complete historical baseline was established."""
    excluded_paths = excluded or set()
    return tuple(
        UpgradeAction(
            kind="conflict",
            path=file.path,
            lifecycle=file.lifecycle,
            reason=(
                "Manifest-less project does not match a complete supported "
                "legacy managed-file baseline."
            ),
        )
        for file in rendered_files
        if file.path not in excluded_paths
    )


def _append_legacy_migrations(
    root: Path,
    *,
    actions: list[UpgradeAction],
    writes: list[TransactionalWrite],
    migration_by_path: dict[Path, StructuredFileChange],
    scoped_paths: set[str] | None,
) -> None:
    """Append structured migration actions for a legacy plan."""
    for path, migration in sorted(migration_by_path.items()):
        if scoped_paths is not None and path.as_posix() not in scoped_paths:
            continue
        action, write = _plan_legacy_migration(root, path=path, migration=migration)
        actions.append(action)
        if write is not None:
            writes.append(write)


def _append_legacy_orphans(
    *,
    actions: list[UpgradeAction],
    legacy_match: _LegacyPlanMatch,
    rendered_by_path: dict[Path, RenderedFile],
    scoped_paths: set[str] | None,
) -> None:
    """Append orphan actions for deselected legacy managed files."""
    desired_paths = {file.path.as_posix() for file in rendered_by_path.values()}
    for path_text in legacy_match.managed_paths:
        if scoped_paths is not None and path_text not in scoped_paths:
            continue
        if path_text in desired_paths:
            continue
        actions.append(
            UpgradeAction(
                kind="orphan",
                path=Path(path_text),
                lifecycle="managed",
                reason="Legacy managed file is no longer selected; left in place.",
            )
        )


def _plan_legacy_file(
    config: GeneratedProjectConfig,
    *,
    file: RenderedFile,
    accepted: set[Path],
    legacy_paths: set[str],
) -> tuple[UpgradeAction, TransactionalWrite | None]:
    """Plan one file in a manifest-less legacy project."""
    current = config.root / file.path
    path_conflict = _path_conflict(config.root, file.path)
    if path_conflict is not None:
        return _conflict_action(file.path, file.lifecycle, path_conflict), None
    if current.is_symlink() or (current.exists() and not current.is_file()):
        return (
            _conflict_action(
                file.path,
                file.lifecycle,
                "Legacy managed target is not a regular file.",
            ),
            None,
        )
    if file.path.as_posix() in legacy_paths:
        return _plan_accepted_legacy_file(current, file=file, accepted=accepted)
    if current.exists():
        return (
            UpgradeAction(
                kind="conflict",
                path=file.path,
                lifecycle=file.lifecycle,
                reason="Existing file is not an exact recognized managed baseline.",
            ),
            None,
        )
    return (
        UpgradeAction(
            kind="add",
            path=file.path,
            lifecycle=file.lifecycle,
            reason="Desired generated file is missing and will be added.",
        ),
        TransactionalWrite(file.path, file.content),
    )


def _plan_legacy_migration(
    root: Path,
    *,
    path: Path,
    migration: StructuredFileChange,
) -> tuple[UpgradeAction, TransactionalWrite | None]:
    """Plan a structured migration in a manifest-less legacy project."""
    current = root / path
    path_conflict = _path_conflict(root, path)
    if path_conflict is not None:
        return _conflict_action(path, "structured", path_conflict), None
    if current.is_symlink() or (current.exists() and not current.is_file()):
        return (
            _conflict_action(
                path,
                "structured",
                "Structured migration target is not a regular file.",
            ),
            None,
        )
    if current.exists() and _read_text(current) == migration.content:
        return _unchanged(path, "structured"), None
    action_kind: UpgradeActionKind = "add" if migration.kind == "create" else "migrate"
    return (
        UpgradeAction(
            kind=action_kind,
            path=path,
            lifecycle="structured",
            reason=migration.description,
        ),
        TransactionalWrite(path, migration.content),
    )


def _plan_accepted_legacy_file(
    current: Path,
    *,
    file: RenderedFile,
    accepted: set[Path],
) -> tuple[UpgradeAction, TransactionalWrite | None]:
    """Plan adoption or update for one exact legacy managed file."""
    if file.path in accepted and not _has_generated_marker(current):
        return (
            UpgradeAction(
                kind="conflict",
                path=file.path,
                lifecycle=file.lifecycle,
                reason="Accepted legacy path is not marker-bearing.",
            ),
            None,
        )
    if _read_bytes(current) == file.content.encode("utf-8"):
        return _unchanged(file.path, file.lifecycle), None
    return (
        UpgradeAction(
            kind="update",
            path=file.path,
            lifecycle=file.lifecycle,
            reason="Legacy managed baseline will be updated.",
        ),
        TransactionalWrite(file.path, file.content),
    )


def _plan_tracked_file(
    root: Path,
    current: ManifestFile,
    desired: RenderedFile,
    *,
    force: bool,
) -> tuple[UpgradeAction, TransactionalWrite | None]:
    """Plan one manifest-tracked file."""
    path = ensure_relative_safe_path(current.path)
    target = root / path
    conflict = _tracked_path_conflict(root, path)
    if conflict is not None:
        return (
            UpgradeAction(kind="conflict", path=path, lifecycle=current.lifecycle, reason=conflict),
            None,
        )
    current_hash = _file_sha256(target)
    if current_hash != current.sha256 and not force:
        return (
            UpgradeAction(
                kind="conflict",
                path=path,
                lifecycle=current.lifecycle,
                reason="Current bytes do not match the manifest baseline.",
            ),
            None,
        )
    if current_hash == content_sha256(desired.content):
        return _unchanged(path, desired.lifecycle), None
    return (
        UpgradeAction(
            kind="update",
            path=path,
            lifecycle=desired.lifecycle,
            reason="Manifest baseline is clean and desired content changed.",
        ),
        TransactionalWrite(path, desired.content),
    )


def _merge_scoped_manifest(
    *,
    current_manifest: ProjectManifest,
    target_manifest: ProjectManifest,
    selected_paths: tuple[Path, ...],
) -> ProjectManifest:
    """Merge scoped target entries into the current manifest."""
    selected_path_text = {path.as_posix() for path in selected_paths}
    target_by_path = {file.path: file for file in target_manifest.files}
    files = [
        target_by_path.get(file.path, file)
        for file in current_manifest.files
        if file.lifecycle == "managed"
        and (file.path not in selected_path_text or file.path in target_by_path)
    ]
    current_paths = {file.path for file in current_manifest.files}
    files.extend(file for file in target_manifest.files if file.path not in current_paths)
    return ProjectManifest(
        manifest_version=MANIFEST_VERSION,
        project_format_version=PROJECT_FORMAT_VERSION,
        generated_with=target_manifest.generated_with,
        requires_scaffold_guard=target_manifest.requires_scaffold_guard,
        profile=target_manifest.profile,
        adapters=target_manifest.adapters,
        files=tuple(sorted(files, key=lambda file: file.path)),
    )


def _plan_migration(
    root: Path,
    path: Path,
    current: ManifestFile | None,
    migration: StructuredFileChange,
) -> tuple[UpgradeAction, TransactionalWrite | None]:
    """Plan one structured migration."""
    target = root / path
    path_conflict = _path_conflict(root, path)
    if path_conflict is not None:
        return (
            UpgradeAction(
                kind="conflict",
                path=path,
                lifecycle="structured",
                reason=path_conflict,
            ),
            None,
        )
    if current is not None:
        conflict = _tracked_path_conflict(root, path)
        if conflict is not None:
            return (
                UpgradeAction(
                    kind="conflict",
                    path=path,
                    lifecycle=current.lifecycle,
                    reason=conflict,
                ),
                None,
            )
        if _file_sha256(target) != current.sha256:
            return (
                UpgradeAction(
                    kind="conflict",
                    path=path,
                    lifecycle=current.lifecycle,
                    reason="Structured file has drifted from the manifest baseline.",
                ),
                None,
            )
    elif target.exists():
        if not target.is_file() or target.is_symlink():
            return (
                UpgradeAction(
                    kind="conflict",
                    path=path,
                    lifecycle="structured",
                    reason="Structured migration target is not a regular file.",
                ),
                None,
            )
    if target.exists() and _read_text(target) == migration.content:
        return _unchanged(path, "structured"), None
    action_kind: UpgradeActionKind = "add" if migration.kind == "create" else "migrate"
    return (
        UpgradeAction(
            kind=action_kind,
            path=path,
            lifecycle="structured",
            reason=migration.description,
        ),
        TransactionalWrite(path, migration.content),
    )


def _plan_add(
    root: Path,
    desired: RenderedFile,
    *,
    force: bool,
) -> tuple[UpgradeAction, TransactionalWrite | None]:
    """Plan a new generated destination."""
    target = root / desired.path
    path_conflict = _path_conflict(root, desired.path, allow_missing_leaf=True)
    if path_conflict is not None:
        return (
            UpgradeAction(
                kind="conflict",
                path=desired.path,
                lifecycle=desired.lifecycle,
                reason=path_conflict,
            ),
            None,
        )
    if target.exists() and not force:
        return (
            UpgradeAction(
                kind="conflict",
                path=desired.path,
                lifecycle=desired.lifecycle,
                reason="New desired managed destination already exists.",
            ),
            None,
        )
    if target.is_symlink():
        return (
            UpgradeAction(
                kind="conflict",
                path=desired.path,
                lifecycle=desired.lifecycle,
                reason="Refusing to write through symbolic link.",
            ),
            None,
        )
    return (
        UpgradeAction(
            kind="add",
            path=desired.path,
            lifecycle=desired.lifecycle,
            reason="Desired generated file is missing and will be added.",
        ),
        TransactionalWrite(desired.path, desired.content),
    )


def _structured_migrations(
    config: GeneratedProjectConfig,
    rendered_files: tuple[RenderedFile, ...],
) -> tuple[StructuredFileChange, ...]:
    """Return applicable structured TOML migrations."""
    desired_content = {file.path: file.content for file in rendered_files}
    migrations: list[StructuredFileChange] = []
    try:
        metadata = plan_project_metadata_migration(
            config.root,
            generated_with=__version__,
            minimum_version=GENERATED_PROJECT_MINIMUM_VERSION,
        )
        if metadata is not None:
            migrations.append(metadata)
        pyproject = plan_dependency_floor_migration(
            config.root,
            desired_content=desired_content.get(Path("pyproject.toml"), ""),
            minimum_version=GENERATED_PROJECT_MINIMUM_VERSION,
            allow_create=(
                config.format_version is None and config.profile in {"minimal", "typescript"}
            ),
        )
        if pyproject is not None:
            migrations.append(pyproject)
    except MigrationError as exc:
        raise UpgradeError(str(exc)) from exc
    return tuple(migrations)


def _structured_path_preflight_conflicts(root: Path) -> tuple[UpgradeAction, ...]:
    """Return conflicts for unsafe structured migration destinations."""
    conflicts: list[UpgradeAction] = []
    for path in sorted(STRUCTURED_MIGRATION_PATHS):
        path_conflict = _path_conflict(root, path)
        if path_conflict is not None:
            conflicts.append(_conflict_action(path, "structured", path_conflict))
            continue
        target = root / path
        if target.exists() and not target.is_file():
            conflicts.append(
                _conflict_action(
                    path,
                    "structured",
                    "Structured migration target is not a regular file.",
                )
            )
    return tuple(conflicts)


def _desired_rendered_files(
    config: GeneratedProjectConfig,
    *,
    paths: tuple[Path, ...] | None,
) -> tuple[RenderedFile, ...]:
    """Render desired generated files, optionally scoped to selected paths."""
    rendered = render_package_files(_config_init_options(config, dry_run=True, force=True))
    if paths is None:
        return tuple(file for file in rendered if _is_lifecycle_managed_file(config, file))
    selected = {path.as_posix() for path in paths}
    return tuple(
        file
        for file in rendered
        if _is_lifecycle_managed_file(config, file) and file.path.as_posix() in selected
    )


def _legacy_plan_match(
    config: GeneratedProjectConfig,
    *,
    legacy_config: LegacyCatalogConfig,
    accepted: set[Path],
) -> _LegacyPlanMatch | None:
    """Return an exact or path-scoped accepted legacy release candidate."""
    if not accepted:
        return _legacy_match(config, legacy_config=legacy_config)
    path_candidates = _legacy_path_candidates(
        config,
        legacy_config=legacy_config,
        accepted=accepted,
    )
    if not path_candidates:
        raise UpgradeError(
            "Accepted legacy paths do not belong to one complete supported legacy file set."
        )
    candidates = _accepted_legacy_candidates(config, legacy_config=legacy_config, accepted=accepted)
    if not candidates:
        return None
    signatures = {_legacy_candidate_signature(legacy_config, candidate) for candidate in candidates}
    if len(signatures) != 1:
        raise UpgradeError("Accepted legacy paths match multiple historical baselines ambiguously.")
    return candidates[-1]


def _validate_accept_legacy_arguments(
    config: GeneratedProjectConfig,
    *,
    legacy_config: LegacyCatalogConfig,
    accepted: set[Path],
) -> None:
    """Validate --accept-legacy arguments before candidate matching."""
    if not accepted:
        return
    recognized = _recognized_legacy_paths(legacy_config)
    for path in accepted:
        path_text = path.as_posix()
        if path_text not in recognized:
            raise UpgradeError(f"Accepted legacy path is not recognized: {path_text}")
        target = config.root / path
        if not target.is_file() or target.is_symlink():
            raise UpgradeError(
                f"Accepted legacy path is missing or not a regular file: {path_text}"
            )
        if not _has_generated_marker(target):
            raise UpgradeError(f"Accepted legacy path is not marker-bearing: {path_text}")


def _accepted_legacy_candidates(
    config: GeneratedProjectConfig,
    *,
    legacy_config: LegacyCatalogConfig,
    accepted: set[Path],
) -> tuple[_LegacyPlanMatch, ...]:
    """Return releases matching all unaccepted paths exactly."""
    matches: list[_LegacyPlanMatch] = []
    recognized = _recognized_legacy_paths(legacy_config)
    for release in LEGACY_RELEASES:
        rendered = render_legacy_managed_files(legacy_config, release=release)
        if not rendered:
            continue
        expected = {file.path: file.content for file in rendered}
        if _accepted_candidate_matches(
            config.root,
            expected=expected,
            accepted=accepted,
            recognized=recognized,
        ):
            matches.append(_LegacyPlanMatch(release=release, managed_paths=tuple(expected)))
    return tuple(matches)


def _legacy_path_candidates(
    config: GeneratedProjectConfig,
    *,
    legacy_config: LegacyCatalogConfig,
    accepted: set[Path],
) -> tuple[_LegacyPlanMatch, ...]:
    """Return releases whose complete recognized path set matches the project."""
    accepted_text = {path.as_posix() for path in accepted}
    recognized = _recognized_legacy_paths(legacy_config)
    actual = _present_recognized_legacy_paths(config.root, recognized)
    matches: list[_LegacyPlanMatch] = []
    for release in LEGACY_RELEASES:
        expected = legacy_managed_paths(legacy_config, release=release)
        if not expected:
            continue
        expected_set = frozenset(expected)
        if accepted_text.issubset(expected_set) and actual == expected_set:
            matches.append(_LegacyPlanMatch(release=release, managed_paths=expected))
    return tuple(matches)


def _accepted_candidate_matches(
    root: Path,
    *,
    expected: dict[str, str],
    accepted: set[Path],
    recognized: frozenset[str],
) -> bool:
    """Return whether one legacy release matches with scoped accepted drift."""
    accepted_text = {path.as_posix() for path in accepted}
    if not accepted_text.issubset(expected):
        return False
    if _present_recognized_legacy_paths(root, recognized) != frozenset(expected):
        return False
    for path_text, content in expected.items():
        path = root / path_text
        if not path.is_file() or path.is_symlink():
            return False
        if path_text in accepted_text:
            if not _has_generated_marker(path):
                return False
            continue
        if _read_bytes(path) != content.encode("utf-8"):
            return False
    return True


def _legacy_match(
    config: GeneratedProjectConfig,
    *,
    legacy_config: LegacyCatalogConfig,
) -> _LegacyPlanMatch | None:
    """Return the exact legacy managed baseline match for a manifest-less project."""
    candidates = _accepted_legacy_candidates(
        config,
        legacy_config=legacy_config,
        accepted=set(),
    )
    return None if not candidates else candidates[-1]


def _recognized_legacy_paths(legacy_config: LegacyCatalogConfig) -> frozenset[str]:
    """Return every legacy managed path recognized for the current config surface."""
    profiles: tuple[ProfileChoice, ...] = ("minimal", "python", "typescript", "monorepo")
    ci_choices: tuple[CiChoice, ...] = ("github", "gitlab")
    surfaces = tuple(
        LegacyCatalogConfig(
            profile=profile,
            adapters=("codex", "claude", "cursor"),
            ci=ci,
            render_context=legacy_config.render_context,
        )
        for profile in profiles
        for ci in ci_choices
    )
    return frozenset(
        path
        for surface in surfaces
        for release in LEGACY_RELEASES
        for path in legacy_managed_paths(surface, release=release)
    )


def _present_recognized_legacy_paths(
    root: Path,
    recognized: frozenset[str],
) -> frozenset[str]:
    """Return recognized paths present in any filesystem form."""
    return frozenset(
        path_text
        for path_text in recognized
        if (root / path_text).exists() or (root / path_text).is_symlink()
    )


def _legacy_candidate_signature(
    legacy_config: LegacyCatalogConfig,
    candidate: _LegacyPlanMatch,
) -> tuple[tuple[str, str], ...]:
    """Return rendered candidate content used to reject accepted-path ambiguity."""
    return tuple(
        (file.path, file.content)
        for file in render_legacy_managed_files(legacy_config, release=candidate.release)
    )


def _legacy_catalog_config(config: GeneratedProjectConfig) -> LegacyCatalogConfig:
    """Build a legacy catalog config from generated-project config."""
    options = _config_init_options(config, dry_run=True, force=True)
    return LegacyCatalogConfig(
        profile=options.profile,
        adapters=config.adapters,
        ci=options.ci,
        render_context=build_render_context(options),
    )


def _tracked_path_conflict(root: Path, path: Path) -> str | None:
    """Return a conflict reason for unsafe tracked paths."""
    path_conflict = _path_conflict(root, path)
    if path_conflict is not None:
        return path_conflict
    target = root / path
    if not target.exists():
        return "Manifest-tracked file is missing."
    if target.is_symlink():
        return "Manifest-tracked path is a symbolic link."
    if not target.is_file():
        return "Manifest-tracked path is not a regular file."
    return None


def _path_conflict(root: Path, path: Path, *, allow_missing_leaf: bool = False) -> str | None:
    """Return a conflict reason for escaping paths or symlink components."""
    safe_path = ensure_relative_safe_path(path.as_posix())
    target = root / safe_path
    if not is_within_directory(root, target):
        return "Generated path escapes the project root."
    current = root
    parts = safe_path.parts[:-1] if allow_missing_leaf else safe_path.parts
    for part in parts:
        current = current / part
        if current.is_symlink():
            return "Generated path contains a symbolic-link component."
    return None


def _manifest_write(manifest: ProjectManifest) -> TransactionalWrite:
    """Return the final manifest transaction write."""
    return TransactionalWrite(Path(MANIFEST_RELATIVE_PATH), manifest_json(manifest))


def _existing_manifest_action(
    root: Path,
    *,
    current: ProjectManifest,
    target: ProjectManifest,
) -> UpgradeAction:
    """Return the action required for an existing managed-file manifest."""
    target_path = root / MANIFEST_RELATIVE_PATH
    if target_path.read_bytes() == manifest_json(target).encode("utf-8"):
        return UpgradeAction(
            kind="unchanged",
            path=Path(MANIFEST_RELATIVE_PATH),
            lifecycle=None,
            reason="Managed-file manifest already matches the target state.",
        )
    if current == target:
        return UpgradeAction(
            kind="migrate",
            path=Path(MANIFEST_RELATIVE_PATH),
            lifecycle=None,
            reason="Canonicalize managed-file manifest serialization.",
        )
    return UpgradeAction(
        kind="update",
        path=Path(MANIFEST_RELATIVE_PATH),
        lifecycle=None,
        reason="Update managed-file manifest metadata and baselines.",
    )


def _legacy_manifest_action() -> UpgradeAction:
    """Return the manifest creation action for a legacy project."""
    return UpgradeAction(
        kind="add",
        path=Path(MANIFEST_RELATIVE_PATH),
        lifecycle=None,
        reason="Create the v0.2 managed-file manifest after successful adoption.",
    )


def _targeted_verification(root: Path) -> CheckReport:
    """Run the health checks targeted by upgrade apply."""
    return CheckReport(
        path=root,
        checks=(
            check_project_health(root),
            check_generated_files(root),
            check_config_consistency(root),
        ),
    )


def _config_init_options(
    config: GeneratedProjectConfig,
    *,
    dry_run: bool,
    force: bool,
) -> InitOptions:
    """Build init options while preserving exact configured adapters."""
    return InitOptions(
        target_dir=config.root,
        project_slug=config.name,
        package_name=config.package,
        agent=config.agent_choice,
        profile=config.profile,
        license="MIT",
        python_min=config.python_min,
        coverage=config.coverage_fail_under,
        ci=config.ci,
        docs_enabled=config.docs,
        dry_run=dry_run,
        force=force,
        ruff_enabled=config.ruff,
        mypy_enabled=config.mypy,
        pyright_enabled=config.pyright,
        ruff_mode=config.ruff_mode,
        python_typecheck_mode=config.python_typecheck_mode,
        python_typechecker=config.python_typechecker,
        typescript_strict_enabled=config.typescript_strict,
        biome_enabled=config.biome,
        vitest_enabled=config.vitest,
        adapter_selection=config.adapters,
    )


def _run_uv_lock(root: Path) -> None:
    """Refresh an existing uv lockfile without invoking a shell."""
    uv_path = shutil.which("uv")
    if uv_path is None:
        raise UpgradeError("uv was not found on PATH; cannot refresh uv.lock.")
    result = asyncio.run(_run_uv_lock_process(uv_path, root))
    if result[0] != 0:
        detail = result[2].strip() or result[1].strip() or "uv lock failed"
        raise UpgradeError(detail)


async def _run_uv_lock_process(uv_path: str, root: Path) -> tuple[int, str, str]:
    """Run uv lock asynchronously using the repository subprocess pattern."""
    process = await asyncio.create_subprocess_exec(
        uv_path,
        "lock",
        cwd=root,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return (
        process.returncode or 0,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


def _metadata_from_manifest(manifest: ProjectManifest) -> UpgradeMetadata:
    """Return current metadata for a manifest project."""
    return UpgradeMetadata(
        manifest_version=manifest.manifest_version,
        project_format_version=manifest.project_format_version,
        profile=manifest.profile,
        adapters=manifest.adapters,
        generated_with=manifest.generated_with,
        requires_scaffold_guard=manifest.requires_scaffold_guard,
    )


def _legacy_metadata(
    config: GeneratedProjectConfig,
    legacy_match: _LegacyPlanMatch | None,
) -> UpgradeMetadata:
    """Return current metadata for a legacy project."""
    return UpgradeMetadata(
        manifest_version=None,
        project_format_version=None,
        profile=config.profile,
        adapters=config.adapters,
        generated_with=config.generated_with,
        requires_scaffold_guard=config.requires_scaffold_guard,
        legacy_release=None if legacy_match is None else legacy_match.release,
    )


def _target_metadata(config: GeneratedProjectConfig) -> UpgradeMetadata:
    """Return target v0.2 project metadata."""
    return UpgradeMetadata(
        manifest_version=MANIFEST_VERSION,
        project_format_version=PROJECT_FORMAT_VERSION,
        profile=config.profile,
        adapters=config.adapters,
        generated_with=__version__,
        requires_scaffold_guard=f">={GENERATED_PROJECT_MINIMUM_VERSION}",
    )


def _ordered_actions(actions: list[UpgradeAction]) -> tuple[UpgradeAction, ...]:
    """Return actions in the public stable ordering."""
    order = {kind: index for index, kind in enumerate(ACTION_ORDER)}
    return tuple(sorted(actions, key=lambda action: (order[action.kind], action.path.as_posix())))


def _preflight_accept_legacy_paths(
    root: Path,
    paths: tuple[Path, ...],
) -> tuple[set[Path], list[UpgradeAction]]:
    """Normalize accepted paths and return filesystem-safety conflicts."""
    accepted: set[Path] = set()
    conflicts: list[UpgradeAction] = []
    for raw_path in paths:
        try:
            path = ensure_relative_safe_path(raw_path.as_posix())
        except ValueError as exc:
            conflicts.append(_conflict_action(raw_path, "managed", str(exc)))
            continue
        path_conflict = _path_conflict(root, path)
        if path_conflict is not None:
            conflicts.append(_conflict_action(path, "managed", path_conflict))
            continue
        target = root / path
        if target.is_symlink() or (target.exists() and not target.is_file()):
            conflicts.append(
                _conflict_action(
                    path,
                    "managed",
                    "Accepted legacy target is not a regular file.",
                )
            )
            continue
        accepted.add(path)
    return accepted, conflicts


def _has_generated_marker(path: Path) -> bool:
    """Return whether a legacy file carries a ScaffoldGuard generated marker."""
    content = _read_text(path)
    return "generated by scaffold-guard" in content or "scaffold-guard generated" in content


def _read_text(path: Path) -> str:
    """Read UTF-8 text and normalize failures as upgrade errors."""
    try:
        return _read_bytes(path).decode("utf-8")
    except UnicodeDecodeError as exc:
        msg = f"Unable to read UTF-8 generated file: {path}"
        raise UpgradeError(msg) from exc


def _read_bytes(path: Path) -> bytes:
    """Read exact file bytes without newline normalization."""
    try:
        return path.read_bytes()
    except OSError as exc:
        msg = f"Unable to read generated file: {path}"
        raise UpgradeError(msg) from exc


def _validate_manifest_metadata(
    config: GeneratedProjectConfig,
    manifest: ProjectManifest,
) -> None:
    """Validate generated config and manifest metadata agree before mutation."""
    if manifest.project_format_version != config.format_version:
        raise UpgradeError("Manifest project format does not match scaffold-guard.toml.")
    if manifest.generated_with != config.generated_with:
        raise UpgradeError("Manifest generated_with does not match scaffold-guard.toml.")
    if manifest.requires_scaffold_guard != config.requires_scaffold_guard:
        raise UpgradeError("Manifest requires_scaffold_guard does not match scaffold-guard.toml.")


def _file_sha256(path: Path) -> str:
    """Return the SHA-256 digest of exact file bytes."""
    return bytes_sha256(path.read_bytes())


def _conflict_action(
    path: Path,
    lifecycle: TemplateLifecycle,
    reason: str,
) -> UpgradeAction:
    """Return one filesystem preflight conflict action."""
    return UpgradeAction(kind="conflict", path=path, lifecycle=lifecycle, reason=reason)


def _unchanged(path: Path, lifecycle: TemplateLifecycle) -> UpgradeAction:
    """Return an unchanged action."""
    return UpgradeAction(
        kind="unchanged",
        path=path,
        lifecycle=lifecycle,
        reason="Current content already matches the desired generated content.",
    )


def _is_lifecycle_managed_file(config: GeneratedProjectConfig, file: RenderedFile) -> bool:
    """Return whether upgrade should reconcile a rendered managed file."""
    if file.lifecycle != "managed":
        return False
    path = file.path.as_posix()
    selected = True
    if path == "CLAUDE.md" or path.startswith(".claude/"):
        selected = "claude" in config.adapters
    elif path.startswith(".cursor/"):
        selected = "cursor" in config.adapters
    elif path.startswith(".codex/"):
        selected = "codex" in config.adapters
    elif path.startswith(".github/workflows/"):
        selected = config.github_actions and (path != ".github/workflows/docs.yml" or config.docs)
    elif path == ".gitlab-ci.yml":
        selected = config.gitlab_ci
    return selected


def _needs_lock(
    root: Path,
    writes: tuple[TransactionalWrite, ...] | list[TransactionalWrite],
) -> bool:
    """Return whether writes should refresh an existing uv lockfile."""
    return (root / "uv.lock").exists() and any(
        write.path == Path("pyproject.toml") for write in writes
    )
