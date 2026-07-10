"""Structured migrations for versioned generated projects."""

from collections.abc import Mapping, MutableSequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, cast

import tomlkit
from packaging.requirements import InvalidRequirement, Requirement
from tomlkit.items import Array, InlineTable, Table

from scaffold_guard.versions import PROJECT_FORMAT_VERSION, PROJECT_METADATA_KEYS

MigrationKind = Literal["create", "migrate"]


class _TableReader(Protocol):
    """Typed read boundary for tomlkit's untyped mapping API."""

    def get(self, key: str) -> object | None:
        """Return one TOML item when present."""
        ...


class MigrationError(ValueError):
    """Raised when a structured file cannot be migrated safely."""


@dataclass(frozen=True, slots=True)
class StructuredFileChange:
    """One complete structured-file replacement produced by a safe migration."""

    path: Path
    kind: MigrationKind
    description: str
    content: str


def plan_project_metadata_migration(
    root: Path,
    *,
    generated_with: str,
    minimum_version: str,
) -> StructuredFileChange | None:
    """Plan the reserved ScaffoldGuard metadata table migration."""
    path = _safe_structured_file_path(root, "scaffold-guard.toml")
    if not path.is_file():
        msg = f"Generated project config is missing: {path}"
        raise MigrationError(msg)
    original = path.read_text(encoding="utf-8")
    document = _parse_toml(original, path)
    metadata_present = "scaffold_guard" in document
    metadata_value = _table_value(document, "scaffold_guard")
    if metadata_value is None and not metadata_present:
        metadata = tomlkit.table()
        document["scaffold_guard"] = metadata
    elif isinstance(metadata_value, Table):
        if not metadata_value:
            msg = "scaffold-guard.toml [scaffold_guard] must not be empty."
            raise MigrationError(msg)
        metadata = metadata_value
    else:
        msg = "scaffold-guard.toml [scaffold_guard] must be a table."
        raise MigrationError(msg)

    unknown_keys = set(cast("Mapping[str, object]", metadata)) - PROJECT_METADATA_KEYS
    if unknown_keys:
        unknown_key = sorted(unknown_keys)[0]
        raise MigrationError(
            f"scaffold-guard.toml [scaffold_guard] contains unsupported key: {unknown_key}"
        )

    metadata["format_version"] = PROJECT_FORMAT_VERSION
    metadata["generated_with"] = generated_with
    metadata["requires_scaffold_guard"] = f">={minimum_version}"
    rendered = tomlkit.dumps(document)
    if rendered == original:
        return None
    return StructuredFileChange(
        path=Path("scaffold-guard.toml"),
        kind="migrate",
        description="Add or update versioned ScaffoldGuard project metadata.",
        content=rendered,
    )


def plan_dependency_floor_migration(
    root: Path,
    *,
    desired_content: str,
    minimum_version: str,
    allow_create: bool,
) -> StructuredFileChange | None:
    """Plan a precise generated-project ScaffoldGuard dependency-floor migration."""
    path = _safe_structured_file_path(root, "pyproject.toml")
    if not path.exists():
        if not allow_create:
            msg = f"pyproject.toml is unexpectedly missing: {path}"
            raise MigrationError(msg)
        _parse_toml(desired_content, path)
        return StructuredFileChange(
            path=Path("pyproject.toml"),
            kind="create",
            description="Create the generated tool-carrier pyproject.toml.",
            content=desired_content,
        )
    if not path.is_file():
        msg = f"pyproject.toml is not a regular file: {path}"
        raise MigrationError(msg)

    original = path.read_text(encoding="utf-8")
    document = _parse_toml(original, path)
    _refuse_scaffold_guard_source_override(document)
    dependency_groups = _dependency_groups_table(document)
    dev = _development_dependency_array(dependency_groups)
    matching_indexes = _scaffold_guard_requirement_indexes(dev)
    if not matching_indexes:
        raise MigrationError(
            "pyproject.toml has no scaffold-guard development requirement to migrate."
        )
    if len(matching_indexes) > 1:
        raise MigrationError(
            "pyproject.toml contains duplicate scaffold-guard development requirements."
        )

    requirement_text = f"scaffold-guard>={minimum_version}"
    index = next(iter(matching_indexes))
    existing = _requirement_from_value(dev[index])
    _reject_incompatible_scaffold_guard_requirement(existing)
    if str(existing) == requirement_text:
        return None
    dev[index] = requirement_text

    rendered = tomlkit.dumps(document)
    if rendered == original:
        return None
    return StructuredFileChange(
        path=Path("pyproject.toml"),
        kind="migrate",
        description=f"Require {requirement_text} for repo-local commands.",
        content=rendered,
    )


def _safe_structured_file_path(root: Path, filename: str) -> Path:
    """Return a project-root file path after rejecting symlinks below the resolved root."""
    resolved_root = root.resolve(strict=False)
    path = resolved_root / filename
    symlink = _first_symlink_component(resolved_root, path)
    if symlink is not None:
        msg = (
            f"Refusing to use {filename} because symbolic links are not allowed below "
            f"the project root: {symlink}"
        )
        raise MigrationError(msg)
    return path


def _first_symlink_component(root: Path, path: Path) -> Path | None:
    """Return the first symlink component from `root` down to `path`, excluding root."""
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        if current.is_symlink():
            return current
    return None


def _reject_incompatible_scaffold_guard_requirement(requirement: Requirement) -> None:
    """Allow only the generated simple scaffold-guard requirement entry."""
    if requirement.name != "scaffold-guard":
        raise MigrationError(
            "A custom scaffold-guard requirement name cannot be migrated automatically."
        )
    if requirement.extras:
        raise MigrationError(
            "A scaffold-guard requirement with extras cannot be migrated automatically."
        )
    if requirement.marker is not None:
        raise MigrationError(
            "A scaffold-guard requirement with environment markers cannot be migrated "
            "automatically."
        )
    if requirement.url is not None:
        raise MigrationError(
            "A direct URL/path scaffold-guard requirement cannot be migrated automatically."
        )
    specifiers = tuple(requirement.specifier)
    if len(specifiers) != 1 or specifiers[0].operator != ">=":
        raise MigrationError(
            "A custom scaffold-guard version requirement cannot be migrated automatically."
        )


def _parse_toml(content: str, path: Path) -> tomlkit.TOMLDocument:
    """Parse TOML and normalize parse failures for CLI reporting."""
    try:
        return tomlkit.parse(content)
    except (TypeError, ValueError) as exc:
        msg = f"Unable to parse {path.name}: {exc}"
        raise MigrationError(msg) from exc


def _refuse_scaffold_guard_source_override(document: tomlkit.TOMLDocument) -> None:
    """Reject project-specific source overrides that change requirement semantics."""
    tool_value = _table_value(document, "tool")
    if not isinstance(tool_value, (Table, InlineTable)):
        return
    uv_value = _table_value(tool_value, "uv")
    if not isinstance(uv_value, (Table, InlineTable)):
        return
    sources_value = _table_value(uv_value, "sources")
    if isinstance(sources_value, (Table, InlineTable)) and "scaffold-guard" in sources_value:
        raise MigrationError(
            "A [tool.uv.sources] scaffold-guard override cannot be migrated automatically."
        )


def _dependency_groups_table(document: tomlkit.TOMLDocument) -> Table:
    """Return the existing dependency-groups table."""
    value = _table_value(document, "dependency-groups")
    if value is None:
        raise MigrationError("pyproject.toml has no [dependency-groups] table to migrate.")
    if not isinstance(value, Table):
        raise MigrationError("pyproject.toml [dependency-groups] must be a table.")
    return value


def _development_dependency_array(dependency_groups: Table) -> Array:
    """Return the existing development dependency array."""
    value = _table_value(dependency_groups, "dev")
    if value is None:
        raise MigrationError("pyproject.toml has no dependency-groups.dev array to migrate.")
    if not isinstance(value, Array):
        raise MigrationError("pyproject.toml dependency-groups.dev must be an array.")
    return value


def _scaffold_guard_requirement_indexes(dev: Array) -> tuple[int, ...]:
    """Return indexes for normalized ScaffoldGuard development requirements."""
    indexes: list[int] = []
    for index, value in enumerate(cast("MutableSequence[object]", dev)):
        requirement = _requirement_from_value(value)
        if requirement.name.lower().replace("_", "-") == "scaffold-guard":
            indexes.append(index)
    return tuple(indexes)


def _requirement_from_value(value: object) -> Requirement:
    """Parse one dependency-group value as a PEP 508 requirement."""
    if not isinstance(value, str):
        raise MigrationError("pyproject.toml development requirements must be strings.")
    try:
        return Requirement(value)
    except InvalidRequirement as exc:
        msg = f"Invalid development requirement: {value}"
        raise MigrationError(msg) from exc


def _table_value(
    table_value: tomlkit.TOMLDocument | Table | InlineTable,
    key: str,
) -> object | None:
    """Read one loosely typed tomlkit item through a typed boundary."""
    return cast("_TableReader", table_value).get(key)
