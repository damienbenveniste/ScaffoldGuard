"""Integration acceptance tests for `scaffold-guard upgrade`."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from typer.testing import CliRunner

from scaffold_guard.cli import app
from scaffold_guard.legacy import (
    LEGACY_RELEASES,
    LegacyCatalogConfig,
    LegacyRelease,
    render_legacy_managed_files,
)
from scaffold_guard.manifest import MANIFEST_RELATIVE_PATH
from scaffold_guard.scaffold import build_init_options, build_render_context
from scaffold_guard.upgrade import ACTION_ORDER

SUCCESS = 0
CONFLICT = 1
CONFIG_ERROR = 2
REQUIRED_JSON_FIELDS = {
    "ok",
    "path",
    "applied",
    "current",
    "target",
    "actions",
    "conflicts",
    "post_apply_verification",
}


def test_upgrade_default_preview_is_read_only_with_ordered_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preview reports ordered action kinds and does not write files."""
    monkeypatch.chdir(tmp_path)
    project_dir = _legacy_minimal_project(tmp_path)
    before = _snapshot_files(project_dir)

    result = CliRunner().invoke(app, ["upgrade", "--path", str(project_dir), "--json"])

    assert result.exit_code == SUCCESS, result.output
    assert _snapshot_files(project_dir) == before
    payload = _json_payload(result.output)
    assert payload["ok"] is True
    assert payload["applied"] is False
    assert payload["post_apply_verification"] is None
    assert _action_kinds(payload) == sorted(
        _action_kinds(payload),
        key=ACTION_ORDER.index,
    )


def test_upgrade_apply_changes_then_second_apply_preserves_managed_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Apply writes the upgrade once and a second apply leaves managed files untouched."""
    monkeypatch.chdir(tmp_path)
    project_dir = _legacy_minimal_project(tmp_path)

    first_result = CliRunner().invoke(
        app,
        ["upgrade", "--path", str(project_dir), "--apply", "--json"],
    )

    assert first_result.exit_code == SUCCESS, first_result.output
    first_payload = _json_payload(first_result.output)
    assert first_payload["applied"] is True
    assert (project_dir / MANIFEST_RELATIVE_PATH).is_file()
    managed_paths = _managed_manifest_paths(project_dir)
    managed_before = _file_bytes_and_mtimes(project_dir, managed_paths)

    second_result = CliRunner().invoke(
        app,
        ["upgrade", "--path", str(project_dir), "--apply", "--json"],
    )

    assert second_result.exit_code == SUCCESS, second_result.output
    second_payload = _json_payload(second_result.output)
    assert second_payload["applied"] is True
    assert all(kind == "unchanged" for kind in _action_kinds(second_payload))
    assert _file_bytes_and_mtimes(project_dir, managed_paths) == managed_before


def test_upgrade_json_success_uses_exact_contract_fields(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Successful JSON output exposes the public v0.2 upgrade contract only."""
    project_dir = generated_project(tmp_path, profile="minimal", agent="codex")

    result = CliRunner().invoke(app, ["upgrade", "--path", str(project_dir), "--json"])

    assert result.exit_code == SUCCESS, result.output
    payload = _json_payload(result.output)
    assert set(payload) == REQUIRED_JSON_FIELDS
    assert payload["ok"] is True
    assert payload["path"] == str(project_dir)
    assert payload["applied"] is False
    assert isinstance(payload["current"], dict)
    assert isinstance(payload["target"], dict)
    assert isinstance(payload["actions"], list)
    assert payload["conflicts"] == []
    assert payload["post_apply_verification"] is None


def test_managed_drift_preview_and_apply_exit_one_without_writing(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Managed drift is rejected in preview and apply with populated JSON conflicts."""
    project_dir = generated_project(tmp_path, profile="minimal", agent="codex")
    agents_path = project_dir / "AGENTS.md"
    agents_path.write_text(
        f"{agents_path.read_text(encoding='utf-8')}\n- Local unmanaged edit.\n",
        encoding="utf-8",
    )
    before = _snapshot_files(project_dir)

    for args in (["--json"], ["--apply", "--json"]):
        result = CliRunner().invoke(app, ["upgrade", "--path", str(project_dir), *args])
        assert result.exit_code == CONFLICT, result.output
        assert _snapshot_files(project_dir) == before
        payload = _json_payload(result.output)
        assert payload["ok"] is False
        assert payload["applied"] is False
        conflicts = _conflicts(payload)
        assert conflicts
        assert conflicts[0]["path"] == "AGENTS.md"


@pytest.mark.parametrize("case", ["config-only", "partial"])
def test_manifestless_incomplete_baseline_apply_conflicts_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    """Config-only and partial legacy projects cannot be adopted or receive a manifest."""
    monkeypatch.chdir(tmp_path)
    project_dir = _legacy_minimal_project(tmp_path)
    if case == "config-only":
        for path in project_dir.rglob("*"):
            if path.is_file() and path.name != "scaffold-guard.toml":
                path.unlink()
    else:
        (project_dir / "AGENTS.md").unlink()
    before = _snapshot_files(project_dir)

    result = CliRunner().invoke(
        app,
        ["upgrade", "--path", str(project_dir), "--apply", "--json"],
    )

    assert result.exit_code == CONFLICT, result.output
    assert _snapshot_files(project_dir) == before
    assert not (project_dir / MANIFEST_RELATIVE_PATH).exists()
    payload = _json_payload(result.output)
    assert payload["applied"] is False
    managed_actions = [
        action for action in _actions(payload) if action.get("lifecycle") == "managed"
    ]
    assert managed_actions
    assert all(action["kind"] == "conflict" for action in managed_actions)


@pytest.mark.parametrize(
    "case_name",
    [
        "invalid config",
        "unsupported format",
        "malformed manifest",
        "symlink manifest",
    ],
)
def test_upgrade_planning_errors_exit_two_with_json_contract(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    case_name: str,
) -> None:
    """Invalid planning inputs keep the JSON contract while exiting with config errors."""
    project_dir = generated_project(tmp_path, profile="minimal", agent="codex")
    mutate = _PLANNING_ERROR_MUTATIONS[case_name]
    mutate(project_dir)

    result = CliRunner().invoke(app, ["upgrade", "--path", str(project_dir), "--json"])

    assert result.exit_code == CONFIG_ERROR, f"{case_name}: {result.output}"
    payload = _json_payload(result.output)
    assert set(payload) >= REQUIRED_JSON_FIELDS
    assert payload["ok"] is False
    assert payload["path"] == str(project_dir)
    assert payload["applied"] is False
    assert payload["current"] is None
    assert payload["target"] is None
    assert payload["actions"] == []
    assert payload["conflicts"] == []
    assert payload["post_apply_verification"] is None
    error = payload.get("error")
    assert isinstance(error, str)
    assert error


def test_accept_legacy_is_repeatable_for_one_marker_bearing_edit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated accept flags permit one marker-bearing legacy edit."""
    monkeypatch.chdir(tmp_path)
    project_dir = _legacy_minimal_project(tmp_path)
    agents_path = project_dir / "AGENTS.md"
    agents_path.write_text(
        agents_path.read_text(encoding="utf-8").replace(
            "# Agent Instructions",
            "# Local Agent Instructions",
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "upgrade",
            "--path",
            str(project_dir),
            "--json",
            "--accept-legacy",
            "AGENTS.md",
            "--accept-legacy",
            "AGENTS.md",
        ],
    )

    assert result.exit_code == SUCCESS, result.output
    payload = _json_payload(result.output)
    assert payload["ok"] is True
    assert not payload["conflicts"]
    assert any(
        action["path"] == "AGENTS.md" and action["kind"] == "update" for action in _actions(payload)
    )


def test_accept_legacy_rejects_unmarked_ci_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unmarked legacy CI files cannot be waived with accept-legacy."""
    monkeypatch.chdir(tmp_path)
    project_dir = _legacy_minimal_project(tmp_path)
    ci_path = project_dir / ".github/workflows/ci.yml"
    ci_path.write_text(
        ci_path.read_text(encoding="utf-8").replace("Validate", "Local Validate"),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "upgrade",
            "--path",
            str(project_dir),
            "--json",
            "--accept-legacy",
            ".github/workflows/ci.yml",
        ],
    )

    assert result.exit_code == CONFIG_ERROR, result.output
    payload = _json_payload(result.output)
    assert payload["ok"] is False
    assert "marker-bearing" in cast("str", payload.get("error", ""))


def test_exact_legacy_baseline_preview_and_apply_without_accept(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exact legacy baselines do not need accept flags for preview or apply."""
    monkeypatch.chdir(tmp_path)
    project_dir = _legacy_minimal_project(tmp_path)

    preview = CliRunner().invoke(app, ["upgrade", "--path", str(project_dir), "--json"])
    apply = CliRunner().invoke(app, ["upgrade", "--path", str(project_dir), "--apply", "--json"])

    assert preview.exit_code == SUCCESS, preview.output
    assert apply.exit_code == SUCCESS, apply.output
    preview_payload = _json_payload(preview.output)
    apply_payload = _json_payload(apply.output)
    assert _metadata(preview_payload, "current")["legacy_release"] == "v0.1.5"
    assert apply_payload["applied"] is True
    assert (project_dir / MANIFEST_RELATIVE_PATH).is_file()


@pytest.mark.parametrize("release", LEGACY_RELEASES)
def test_every_historical_release_upgrades_to_clean_current_project(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    release: LegacyRelease,
) -> None:
    """Each packaged 0.1.x managed baseline can complete a real upgrade apply."""
    project_dir = generated_project(tmp_path, profile="python", agent="codex")
    manifest = _manifest_data(project_dir)
    managed_files = cast("list[dict[str, object]]", manifest["files"])
    for record in managed_files:
        (project_dir / cast("str", record["path"])).unlink()
    (project_dir / MANIFEST_RELATIVE_PATH).unlink()
    _remove_metadata_table(project_dir / "scaffold-guard.toml")

    options = build_init_options(
        "demo",
        base_dir=tmp_path,
        agent="codex",
        profile="python",
        license_name="MIT",
        python_min="3.13",
        coverage=95,
        ci="github",
        dry_run=True,
        force=False,
    )
    legacy_config = LegacyCatalogConfig(
        profile="python",
        adapters=("codex",),
        ci="github",
        render_context=build_render_context(options),
    )
    for file in render_legacy_managed_files(legacy_config, release=release):
        target = project_dir / file.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(file.content.encode("utf-8"))

    apply_result = CliRunner().invoke(
        app,
        ["upgrade", "--path", str(project_dir), "--apply", "--json"],
    )
    clean_preview = CliRunner().invoke(
        app,
        ["upgrade", "--path", str(project_dir), "--json"],
    )

    assert apply_result.exit_code == SUCCESS, f"{release}: {apply_result.output}"
    assert clean_preview.exit_code == SUCCESS, f"{release}: {clean_preview.output}"
    assert all(kind == "unchanged" for kind in _action_kinds(_json_payload(clean_preview.output)))


@pytest.mark.parametrize(
    ("profile", "agent", "expected_adapters"),
    [
        ("minimal", "codex", ["codex"]),
        ("python", "all", ["codex", "claude", "cursor"]),
        ("typescript", "cursor", ["cursor"]),
        ("monorepo", "claude", ["claude"]),
    ],
)
def test_fresh_generated_profiles_are_noop_with_exact_configured_adapters(
    tmp_path: Path,
    profile: str,
    agent: str,
    expected_adapters: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh v0.2 projects preview and apply as no-ops with configured adapters only."""
    monkeypatch.chdir(tmp_path)
    init_result = CliRunner().invoke(app, ["init", "demo", "--profile", profile, "--agent", agent])
    assert init_result.exit_code == SUCCESS, init_result.output
    project_dir = tmp_path / "demo"

    for args in (["--json"], ["--apply", "--json"]):
        result = CliRunner().invoke(app, ["upgrade", "--path", str(project_dir), *args])
        assert result.exit_code == SUCCESS, result.output
        payload = _json_payload(result.output)
        assert payload["ok"] is True
        assert _metadata(payload, "current")["adapters"] == expected_adapters
        assert _metadata(payload, "target")["adapters"] == expected_adapters
        assert all(kind == "unchanged" for kind in _action_kinds(payload))
    assert _manifest_adapters(project_dir) == expected_adapters


def _legacy_minimal_project(tmp_path: Path) -> Path:
    """Create a manifest-less project from an exact historical managed baseline."""
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
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


def _json_payload(output: str) -> dict[str, object]:
    """Parse command output as a JSON object."""
    return cast("dict[str, object]", json.loads(output))


def _action_kinds(payload: dict[str, object]) -> list[str]:
    """Return action kinds from a parsed upgrade payload."""
    return [cast("str", action["kind"]) for action in _actions(payload)]


def _actions(payload: dict[str, object]) -> list[dict[str, object]]:
    """Return action objects from a parsed upgrade payload."""
    return cast("list[dict[str, object]]", payload["actions"])


def _conflicts(payload: dict[str, object]) -> list[dict[str, object]]:
    """Return conflict objects from a parsed upgrade payload."""
    return cast("list[dict[str, object]]", payload["conflicts"])


def _metadata(payload: dict[str, object], key: str) -> dict[str, object]:
    """Return one metadata object from a parsed upgrade payload."""
    return cast("dict[str, object]", payload[key])


def _snapshot_files(root: Path) -> dict[str, bytes]:
    """Return a byte snapshot of regular files below a project root."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def _file_bytes_and_mtimes(root: Path, paths: tuple[str, ...]) -> dict[str, tuple[bytes, int]]:
    """Return exact bytes and nanosecond mtimes for selected project files."""
    return {path: ((root / path).read_bytes(), (root / path).stat().st_mtime_ns) for path in paths}


def _managed_manifest_paths(root: Path) -> tuple[str, ...]:
    """Return manifest-tracked managed paths."""
    data = _manifest_data(root)
    files = cast("list[dict[str, object]]", data["files"])
    return tuple(cast("str", file["path"]) for file in files)


def _manifest_adapters(root: Path) -> list[str]:
    """Return adapters recorded in the generated-project manifest."""
    data = _manifest_data(root)
    return cast("list[str]", data["adapters"])


def _manifest_data(root: Path) -> dict[str, object]:
    """Load manifest JSON as a dictionary."""
    return cast("dict[str, object]", json.loads((root / MANIFEST_RELATIVE_PATH).read_text()))


def _remove_metadata_table(path: Path) -> None:
    """Remove the current reserved metadata table from a generated config fixture."""
    lines = path.read_text(encoding="utf-8").splitlines()
    output: list[str] = []
    in_metadata = False
    for line in lines:
        if line == "[scaffold_guard]":
            in_metadata = True
            continue
        if in_metadata and line.startswith("[") and line.endswith("]"):
            in_metadata = False
        if not in_metadata:
            output.append(line)
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def _write_invalid_config(project_dir: Path) -> None:
    (project_dir / "scaffold-guard.toml").write_text("[project]\nname = 1\n", encoding="utf-8")


def _write_unsupported_format(project_dir: Path) -> None:
    config_path = project_dir / "scaffold-guard.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "format_version = 1",
            "format_version = 99",
        ),
        encoding="utf-8",
    )


def _write_malformed_manifest(project_dir: Path) -> None:
    (project_dir / MANIFEST_RELATIVE_PATH).write_text("{not-json", encoding="utf-8")


def _replace_manifest_with_symlink(project_dir: Path) -> None:
    manifest_path = project_dir / MANIFEST_RELATIVE_PATH
    target = project_dir / ".scaffold-guard/manifest-target.json"
    target.write_bytes(manifest_path.read_bytes())
    manifest_path.unlink()
    manifest_path.symlink_to(target)


_PLANNING_ERROR_MUTATIONS: dict[str, Callable[[Path], None]] = {
    "invalid config": _write_invalid_config,
    "unsupported format": _write_unsupported_format,
    "malformed manifest": _write_malformed_manifest,
    "symlink manifest": _replace_manifest_with_symlink,
}
