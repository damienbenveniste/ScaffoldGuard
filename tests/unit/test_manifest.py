"""Tests for generated project manifest helpers."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from scaffold_guard.manifest import (
    ManifestError,
    ManifestFile,
    ProjectManifest,
    bytes_sha256,
    content_sha256,
    load_manifest,
    manifest_json,
    manifest_to_data,
    write_manifest,
)
from scaffold_guard.versions import MANIFEST_VERSION, PROJECT_FORMAT_VERSION


def test_content_sha256_hashes_utf8_text_deterministically() -> None:
    """Rendered file content hashes are stable for manifest entries."""
    assert content_sha256("hello\n") == content_sha256("hello\n")
    assert content_sha256("hello\n") != content_sha256("hello")


def test_bytes_sha256_preserves_crlf_bytes() -> None:
    """Byte hashing preserves exact newline bytes for on-disk files."""
    assert bytes_sha256(b"hello\r\n") != bytes_sha256(b"hello\n")
    assert content_sha256("hello\r\n") == bytes_sha256(b"hello\r\n")


def test_write_and_load_manifest_round_trip(tmp_path: Path) -> None:
    """Manifest JSON writes and loads into typed models."""
    manifest_path = tmp_path / ".scaffold-guard" / "manifest.json"

    write_manifest(manifest_path, _manifest())

    loaded = load_manifest(manifest_path)
    expected_bytes = manifest_json(_manifest()).encode("utf-8")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert loaded == _manifest()
    assert manifest_path.read_bytes() == expected_bytes
    assert "lifecycle" not in payload["files"][0]
    assert payload["generated_with"] == "0.2.0"
    assert payload["requires_scaffold_guard"] == ">=0.2.0"


def test_manifest_json_is_deterministic_and_sorted() -> None:
    """Manifest serialization is stable and newline-terminated."""
    unsorted = replace(
        _manifest(),
        files=(
            ManifestFile(
                path="z.rules",
                template_id="agents/z",
                sha256=content_sha256("z\n"),
            ),
            *_manifest().files,
        ),
    )
    first = manifest_json(unsorted)
    second = manifest_json(unsorted)

    assert first == second
    assert first.endswith("\n")
    assert json.loads(first)["files"] == [
        {
            "path": "AGENTS.md",
            "sha256": content_sha256("agent rules\n"),
            "template_id": "package/AGENTS.md",
        },
        {
            "path": "z.rules",
            "sha256": content_sha256("z\n"),
            "template_id": "agents/z",
        },
    ]


@pytest.mark.parametrize(
    ("mutated", "message"),
    [
        ({"manifest_version": MANIFEST_VERSION + 1}, "Unsupported manifest version"),
        ({"project_format_version": PROJECT_FORMAT_VERSION + 1}, "Unsupported project format"),
        ({"profile": "package"}, "supported canonical profile"),
        ({"adapters": ["codex", "codex"]}, "unique supported adapters"),
        ({"adapters": ["unknown"]}, "unsupported adapter"),
        ({"generated_with": ""}, "generated_with must be a non-empty string"),
        ({"generated_with": "not a version"}, "valid version"),
        ({"requires_scaffold_guard": ""}, "requires_scaffold_guard must be a non-empty string"),
        ({"requires_scaffold_guard": "not a specifier"}, "valid version specifier"),
    ],
)
def test_load_manifest_rejects_invalid_top_level_fields(
    tmp_path: Path,
    mutated: dict[str, object],
    message: str,
) -> None:
    """Top-level manifest fields are strictly validated."""
    payload: dict[str, object] = dict(manifest_to_data(_manifest()))
    payload.update(mutated)

    with pytest.raises(ManifestError, match=message):
        _write_and_load(tmp_path, payload)


@pytest.mark.parametrize(
    ("files", "message"),
    [
        ([{"path": "/absolute", "template_id": "x", "sha256": "0" * 64}], "safe relative"),
        ([{"path": "../escape", "template_id": "x", "sha256": "0" * 64}], "safe relative"),
        ([{"path": "nested/../escape", "template_id": "x", "sha256": "0" * 64}], "safe relative"),
        ([{"path": "", "template_id": "x", "sha256": "0" * 64}], "safe relative"),
        ([{"path": ".", "template_id": "x", "sha256": "0" * 64}], "safe relative"),
        ([{"path": "C:/absolute", "template_id": "x", "sha256": "0" * 64}], "safe relative"),
        ([{"path": r"C:\absolute", "template_id": "x", "sha256": "0" * 64}], "safe relative"),
        ([{"path": r"server\share", "template_id": "x", "sha256": "0" * 64}], "safe relative"),
        ([{"path": "bad\x00path", "template_id": "x", "sha256": "0" * 64}], "safe relative"),
        ([{"path": "./AGENTS.md", "template_id": "x", "sha256": "0" * 64}], "canonical"),
        ([{"path": "a//b", "template_id": "x", "sha256": "0" * 64}], "canonical"),
        ([{"path": "a/", "template_id": "x", "sha256": "0" * 64}], "canonical"),
        (
            [
                {"path": "b", "template_id": "b", "sha256": "0" * 64},
                {"path": "a", "template_id": "a", "sha256": "1" * 64},
            ],
            "sorted by path",
        ),
        (
            [
                {"path": "a", "template_id": "one", "sha256": "0" * 64},
                {"path": "a", "template_id": "two", "sha256": "1" * 64},
            ],
            "duplicates path",
        ),
        (
            [
                {"path": "a", "template_id": "same", "sha256": "0" * 64},
                {"path": "b", "template_id": "same", "sha256": "1" * 64},
            ],
            "duplicates template_id",
        ),
        ([{"path": "a", "template_id": "a", "sha256": "not-a-sha"}], "SHA-256"),
        ([{"path": "a", "template_id": "a", "sha256": "A" * 64}], "SHA-256"),
        (
            [{"path": "a", "template_id": "a", "sha256": "0" * 64, "lifecycle": "managed"}],
            "unknown key",
        ),
    ],
)
def test_load_manifest_rejects_invalid_file_records(
    tmp_path: Path,
    files: list[dict[str, object]],
    message: str,
) -> None:
    """Managed file records reject unsafe paths and malformed metadata."""
    payload: dict[str, object] = dict(manifest_to_data(_manifest()))
    payload["files"] = files

    with pytest.raises(ManifestError, match=message):
        _write_and_load(tmp_path, payload)


def test_load_manifest_rejects_malformed_json(tmp_path: Path) -> None:
    """Malformed JSON reports a manifest error."""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{", encoding="utf-8")

    with pytest.raises(ManifestError, match="malformed"):
        load_manifest(manifest_path)


def test_load_manifest_rejects_symlink(tmp_path: Path) -> None:
    """Manifest loading does not follow symlinked manifest files."""
    target = tmp_path / "real.json"
    symlink = tmp_path / "manifest.json"
    write_manifest(target, _manifest())
    symlink.symlink_to(target)

    with pytest.raises(ManifestError, match="symbolic link"):
        load_manifest(symlink)


def test_load_manifest_rejects_symlinked_manifest_parent(tmp_path: Path) -> None:
    """Manifest loading refuses a symlinked `.scaffold-guard` directory."""
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    write_manifest(outside / "manifest.json", _manifest())
    (project / ".scaffold-guard").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ManifestError, match="symbolic link parent"):
        load_manifest(project / ".scaffold-guard" / "manifest.json")


def test_write_manifest_rejects_symlinked_manifest_parent(tmp_path: Path) -> None:
    """Manifest writes cannot escape through a symlinked `.scaffold-guard` directory."""
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    (project / ".scaffold-guard").symlink_to(outside, target_is_directory=True)

    with pytest.raises(FileExistsError, match="symbolic link parent"):
        write_manifest(project / ".scaffold-guard" / "manifest.json", _manifest())

    assert not (outside / "manifest.json").exists()


def _write_and_load(tmp_path: Path, payload: object) -> ProjectManifest:
    """Write raw manifest payload JSON and load it."""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    return load_manifest(manifest_path)


def _manifest() -> ProjectManifest:
    """Return a small manifest fixture."""
    return ProjectManifest(
        manifest_version=MANIFEST_VERSION,
        project_format_version=PROJECT_FORMAT_VERSION,
        generated_with="0.2.0",
        requires_scaffold_guard=">=0.2.0",
        profile="python",
        adapters=("codex",),
        files=(
            ManifestFile(
                path="AGENTS.md",
                template_id="package/AGENTS.md",
                sha256=content_sha256("agent rules\n"),
            ),
        ),
    )
