"""Deterministic manifest models and JSON helpers for generated projects."""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TypedDict, cast

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from scaffold_guard.models import (
    ADAPTER_ORDER,
    CANONICAL_PROFILES,
    AdapterSelection,
    CanonicalProfileChoice,
    TemplateLifecycle,
    normalize_adapter_selection,
)
from scaffold_guard.versions import MANIFEST_VERSION, PROJECT_FORMAT_VERSION

MANIFEST_RELATIVE_PATH: str = ".scaffold-guard/manifest.json"
SHA256_PATTERN: re.Pattern[str] = re.compile(r"^[0-9a-f]{64}$")
WINDOWS_DRIVE_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z]:")


class ManifestError(ValueError):
    """Raised when a generated project manifest is malformed or unsupported."""


class ManifestFileData(TypedDict):
    """JSON representation of one managed generated file entry."""

    path: str
    template_id: str
    sha256: str


class ManifestData(TypedDict):
    """JSON representation of the generated project manifest."""

    manifest_version: int
    project_format_version: int
    generated_with: str
    requires_scaffold_guard: str
    profile: CanonicalProfileChoice
    adapters: list[AdapterSelection]
    files: list[ManifestFileData]


@dataclass(frozen=True, slots=True)
class ManifestFile:
    """Metadata for one managed rendered file tracked by ScaffoldGuard."""

    path: str
    template_id: str
    sha256: str

    @property
    def lifecycle(self) -> TemplateLifecycle:
        """Return the implied lifecycle for every persisted manifest record."""
        return "managed"


@dataclass(frozen=True, slots=True)
class ProjectManifest:
    """Stable lifecycle manifest written into generated project roots."""

    manifest_version: int
    project_format_version: int
    generated_with: str
    requires_scaffold_guard: str
    profile: CanonicalProfileChoice
    adapters: tuple[AdapterSelection, ...]
    files: tuple[ManifestFile, ...]


def content_sha256(content: str) -> str:
    """Return the SHA-256 digest for rendered UTF-8 text."""
    return bytes_sha256(content.encode("utf-8"))


def bytes_sha256(content: bytes) -> str:
    """Return the SHA-256 digest for exact file bytes."""
    return hashlib.sha256(content).hexdigest()


def manifest_to_data(manifest: ProjectManifest) -> ManifestData:
    """Convert a manifest model to its stable JSON payload shape."""
    return {
        "manifest_version": manifest.manifest_version,
        "project_format_version": manifest.project_format_version,
        "generated_with": manifest.generated_with,
        "requires_scaffold_guard": manifest.requires_scaffold_guard,
        "profile": manifest.profile,
        "adapters": list(manifest.adapters),
        "files": [
            {
                "path": file.path,
                "template_id": file.template_id,
                "sha256": file.sha256,
            }
            for file in sorted(manifest.files, key=lambda item: item.path)
        ],
    }


def manifest_from_data(data: object) -> ProjectManifest:
    """Validate parsed manifest JSON data into typed manifest models."""
    root = _require_mapping(data, "manifest")
    _require_keys(
        root,
        "manifest",
        {
            "manifest_version",
            "project_format_version",
            "generated_with",
            "requires_scaffold_guard",
            "profile",
            "adapters",
            "files",
        },
    )
    manifest_version = _require_int(root, "manifest_version")
    if manifest_version != MANIFEST_VERSION:
        msg = f"Unsupported manifest version: {manifest_version}"
        raise ManifestError(msg)
    project_format_version = _require_int(root, "project_format_version")
    if project_format_version != PROJECT_FORMAT_VERSION:
        msg = f"Unsupported project format version: {project_format_version}"
        raise ManifestError(msg)
    return ProjectManifest(
        manifest_version=manifest_version,
        project_format_version=project_format_version,
        generated_with=_require_version(root, "generated_with"),
        requires_scaffold_guard=_require_specifier(root, "requires_scaffold_guard"),
        profile=_require_profile(root, "profile"),
        adapters=_require_adapters(root, "adapters"),
        files=_require_manifest_files(root, "files"),
    )


def load_manifest(path: Path) -> ProjectManifest:
    """Load and validate a generated project manifest without following symlinks."""
    _reject_symlinked_manifest_path(path, operation="read")
    if path.is_symlink():
        msg = f"Refusing to read manifest through symbolic link: {path}"
        raise ManifestError(msg)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        msg = f"Manifest JSON is malformed: {path}"
        raise ManifestError(msg) from exc
    return manifest_from_data(data)


def manifest_json(manifest: ProjectManifest) -> str:
    """Return canonical newline-terminated JSON for a manifest."""
    return f"{json.dumps(manifest_to_data(manifest), indent=2, sort_keys=True)}\n"


def write_manifest(path: Path, manifest: ProjectManifest) -> None:
    """Write a manifest as deterministic, newline-terminated JSON."""
    _reject_symlinked_manifest_path(path, operation="write")
    if path.is_symlink():
        msg = f"Refusing to write manifest through symbolic link: {path}"
        raise FileExistsError(msg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(manifest_json(manifest).encode("utf-8"))


def _reject_symlinked_manifest_path(path: Path, *, operation: str) -> None:
    """Reject `.scaffold-guard` symlink directories before manifest I/O."""
    if path.name == "manifest.json" and path.parent.name == ".scaffold-guard":
        try:
            parent_is_symlink = path.parent.is_symlink()
        except OSError as exc:
            msg = f"Unable to inspect manifest parent: {path.parent}"
            raise ManifestError(msg) from exc
        if parent_is_symlink:
            msg = f"Refusing to {operation} manifest through symbolic link parent: {path.parent}"
            if operation == "write":
                raise FileExistsError(msg)
            raise ManifestError(msg)


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    """Return a JSON object mapping or raise a manifest error."""
    if not isinstance(value, dict):
        msg = f"{label} must be a JSON object."
        raise ManifestError(msg)
    raw_mapping = cast("dict[object, object]", value)
    mapping: dict[str, object] = {}
    for raw_key, raw_value in raw_mapping.items():
        if not isinstance(raw_key, str):
            msg = f"{label} contains a non-string key."
            raise ManifestError(msg)
        mapping[raw_key] = raw_value
    return mapping


def _require_keys(mapping: Mapping[str, object], label: str, expected: set[str]) -> None:
    """Require an exact JSON object key set."""
    keys = set(mapping)
    missing = expected - keys
    if missing:
        msg = f"{label} is missing required key: {sorted(missing)[0]}"
        raise ManifestError(msg)
    unknown = keys - expected
    if unknown:
        msg = f"{label} contains unknown key: {sorted(unknown)[0]}"
        raise ManifestError(msg)


def _require_int(mapping: Mapping[str, object], key: str) -> int:
    """Read a JSON integer field, rejecting bools."""
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"{key} must be an integer."
        raise ManifestError(msg)
    return value


def _require_nonempty_str(mapping: Mapping[str, object], key: str) -> str:
    """Read a non-empty JSON string field."""
    value = mapping[key]
    if not isinstance(value, str) or value == "":
        msg = f"{key} must be a non-empty string."
        raise ManifestError(msg)
    return value


def _require_profile(mapping: Mapping[str, object], key: str) -> CanonicalProfileChoice:
    """Read and validate a canonical generated project profile."""
    value = mapping[key]
    if not isinstance(value, str) or value not in CANONICAL_PROFILES:
        msg = f"{key} must be a supported canonical profile."
        raise ManifestError(msg)
    return value


def _require_version(mapping: Mapping[str, object], key: str) -> str:
    """Read and validate a package version string."""
    value = _require_nonempty_str(mapping, key)
    try:
        Version(value)
    except InvalidVersion as exc:
        msg = f"{key} must be a valid version."
        raise ManifestError(msg) from exc
    return value


def _require_specifier(mapping: Mapping[str, object], key: str) -> str:
    """Read and validate a package version specifier string."""
    value = _require_nonempty_str(mapping, key)
    try:
        SpecifierSet(value)
    except InvalidSpecifier as exc:
        msg = f"{key} must be a valid version specifier."
        raise ManifestError(msg) from exc
    return value


def _require_adapters(mapping: Mapping[str, object], key: str) -> tuple[AdapterSelection, ...]:
    """Read and validate exact manifest adapter selections."""
    value = _require_list(mapping, key)
    adapters: list[AdapterSelection] = []
    for adapter in value:
        if not isinstance(adapter, str) or adapter not in ADAPTER_ORDER:
            msg = f"{key} contains an unsupported adapter."
            raise ManifestError(msg)
        adapters.append(adapter)
    try:
        return normalize_adapter_selection(tuple(adapters))
    except ValueError as exc:
        msg = f"{key} must contain unique supported adapters."
        raise ManifestError(msg) from exc


def _require_manifest_files(
    mapping: Mapping[str, object],
    key: str,
) -> tuple[ManifestFile, ...]:
    """Read, validate, and return managed manifest file records."""
    value = _require_list(mapping, key)
    files: list[ManifestFile] = []
    seen_paths: set[str] = set()
    seen_template_ids: set[str] = set()
    previous_path = ""
    for index, item in enumerate(value):
        file_data = _require_mapping(item, f"{key}[{index}]")
        _require_keys(file_data, f"{key}[{index}]", {"path", "template_id", "sha256"})
        path = _require_manifest_path(file_data, "path")
        if path in seen_paths:
            msg = f"{key}[{index}] duplicates path: {path}"
            raise ManifestError(msg)
        if previous_path and path < previous_path:
            msg = f"{key} must be sorted by path."
            raise ManifestError(msg)
        template_id = _require_nonempty_str(file_data, "template_id")
        if template_id in seen_template_ids:
            msg = f"{key}[{index}] duplicates template_id: {template_id}"
            raise ManifestError(msg)
        sha256 = _require_sha256(file_data, "sha256")
        files.append(ManifestFile(path=path, template_id=template_id, sha256=sha256))
        seen_paths.add(path)
        seen_template_ids.add(template_id)
        previous_path = path
    return tuple(files)


def _require_list(mapping: Mapping[str, object], key: str) -> tuple[object, ...]:
    """Read a JSON list field as a typed tuple of objects."""
    value = mapping[key]
    if not isinstance(value, list):
        msg = f"{key} must be a list."
        raise ManifestError(msg)
    return tuple(cast("list[object]", value))


def _require_manifest_path(mapping: Mapping[str, object], key: str) -> str:
    """Read and validate a relative, traversal-free manifest path."""
    value = mapping[key]
    if not isinstance(value, str):
        msg = f"{key} must be a string."
        raise ManifestError(msg)
    if (
        value in {"", "."}
        or "\x00" in value
        or "\\" in value
        or WINDOWS_DRIVE_PATTERN.match(value) is not None
    ):
        msg = f"{key} must be a safe relative path."
        raise ManifestError(msg)
    safe_path = PurePosixPath(value)
    if safe_path.is_absolute() or ".." in safe_path.parts:
        msg = f"{key} must be a safe relative path."
        raise ManifestError(msg)
    canonical_path = safe_path.as_posix()
    if canonical_path != value:
        msg = f"{key} must be a canonical POSIX relative path."
        raise ManifestError(msg)
    return canonical_path


def _require_sha256(mapping: Mapping[str, object], key: str) -> str:
    """Read and validate a lowercase SHA-256 hex digest."""
    value = mapping[key]
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        msg = f"{key} must be a lowercase SHA-256 digest."
        raise ManifestError(msg)
    return value
