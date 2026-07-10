"""Tests for structured generated-project migrations."""

from pathlib import Path

import pytest

from scaffold_guard.migrations import (
    MigrationError,
    plan_dependency_floor_migration,
    plan_project_metadata_migration,
)


def test_project_metadata_migration_preserves_existing_comments(tmp_path: Path) -> None:
    """Reserved metadata is added without dropping user comments."""
    (tmp_path / "scaffold-guard.toml").write_text(
        '# keep this comment\n[project]\nname = "demo"\n',
        encoding="utf-8",
    )

    change = plan_project_metadata_migration(
        tmp_path,
        generated_with="0.2.0",
        minimum_version="0.2.0",
    )

    assert change is not None
    assert change.kind == "migrate"
    assert "# keep this comment" in change.content
    assert "[scaffold_guard]" in change.content
    assert 'generated_with = "0.2.0"' in change.content
    assert 'requires_scaffold_guard = ">=0.2.0"' in change.content


def test_project_metadata_migration_is_idempotent(tmp_path: Path) -> None:
    """Current project metadata requires no structured rewrite."""
    path = tmp_path / "scaffold-guard.toml"
    path.write_text(
        '[project]\nname = "demo"\n\n'
        "[scaffold_guard]\nformat_version = 1\n"
        'generated_with = "0.2.0"\nrequires_scaffold_guard = ">=0.2.0"\n',
        encoding="utf-8",
    )

    change = plan_project_metadata_migration(
        tmp_path,
        generated_with="0.2.0",
        minimum_version="0.2.0",
    )

    assert change is None


def test_project_metadata_migration_rejects_unknown_reserved_key(tmp_path: Path) -> None:
    """The reserved metadata namespace is not extended by guessing."""
    (tmp_path / "scaffold-guard.toml").write_text(
        '[project]\nname = "demo"\n\n[scaffold_guard]\nowner = "custom"\n',
        encoding="utf-8",
    )

    with pytest.raises(MigrationError, match="unsupported key: owner"):
        plan_project_metadata_migration(
            tmp_path,
            generated_with="0.2.0",
            minimum_version="0.2.0",
        )


def test_project_metadata_migration_rejects_empty_reserved_table(tmp_path: Path) -> None:
    """A present but empty metadata table is malformed, not absent legacy metadata."""
    (tmp_path / "scaffold-guard.toml").write_text(
        '[project]\nname = "demo"\n\n[scaffold_guard]\n',
        encoding="utf-8",
    )

    with pytest.raises(MigrationError, match="must not be empty"):
        plan_project_metadata_migration(
            tmp_path,
            generated_with="0.2.0",
            minimum_version="0.2.0",
        )


def test_project_metadata_migration_allows_symlinked_project_root(tmp_path: Path) -> None:
    """Resolving the project-root argument does not make its config a conflict."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "scaffold-guard.toml").write_text(
        '[project]\nname = "demo"\n',
        encoding="utf-8",
    )
    root_link = tmp_path / "project-link"
    root_link.symlink_to(project, target_is_directory=True)

    change = plan_project_metadata_migration(
        root_link,
        generated_with="0.2.0",
        minimum_version="0.2.0",
    )

    assert change is not None
    assert change.path == Path("scaffold-guard.toml")


def test_project_metadata_migration_rejects_symlink_outside_root(tmp_path: Path) -> None:
    """Structured config migration does not follow a file symlink outside root."""
    outside = tmp_path / "outside"
    project = tmp_path / "project"
    outside.mkdir()
    project.mkdir()
    (outside / "scaffold-guard.toml").write_text(
        '[project]\nname = "demo"\n',
        encoding="utf-8",
    )
    (project / "scaffold-guard.toml").symlink_to(outside / "scaffold-guard.toml")

    with pytest.raises(
        MigrationError,
        match="symbolic links are not allowed below the project root",
    ):
        plan_project_metadata_migration(
            project,
            generated_with="0.2.0",
            minimum_version="0.2.0",
        )


def test_project_metadata_migration_rejects_symlink_within_root(tmp_path: Path) -> None:
    """Structured config migration treats an in-root file symlink as a conflict."""
    project = tmp_path / "project"
    project.mkdir()
    target = project / "real-scaffold-guard.toml"
    target.write_text('[project]\nname = "demo"\n', encoding="utf-8")
    (project / "scaffold-guard.toml").symlink_to(target.name)

    with pytest.raises(
        MigrationError,
        match="symbolic links are not allowed below the project root",
    ):
        plan_project_metadata_migration(
            project,
            generated_with="0.2.0",
            minimum_version="0.2.0",
        )


def test_project_metadata_migration_rejects_non_table_reserved_metadata(
    tmp_path: Path,
) -> None:
    """A scalar scaffold_guard key is malformed instead of legacy-compatible."""
    (tmp_path / "scaffold-guard.toml").write_text(
        'scaffold_guard = "bad"\n\n[project]\nname = "demo"\n',
        encoding="utf-8",
    )

    with pytest.raises(MigrationError, match="must be a table"):
        plan_project_metadata_migration(
            tmp_path,
            generated_with="0.2.0",
            minimum_version="0.2.0",
        )


def test_dependency_floor_migration_updates_only_scaffold_guard(tmp_path: Path) -> None:
    """The dependency floor changes while comments and neighboring entries remain."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n'
        "\n[dependency-groups]\ndev = [\n"
        '  # keep this comment\n  "pytest>=8",\n  "scaffold-guard>=0.1.3",\n]\n',
        encoding="utf-8",
    )

    change = plan_dependency_floor_migration(
        tmp_path,
        desired_content="",
        minimum_version="0.2.0",
        allow_create=False,
    )

    assert change is not None
    assert change.kind == "migrate"
    assert "# keep this comment" in change.content
    assert '"pytest>=8"' in change.content
    assert '"scaffold-guard>=0.2.0"' in change.content
    assert "0.1.3" not in change.content


def test_dependency_floor_migration_creates_expected_legacy_tool_project(
    tmp_path: Path,
) -> None:
    """Legacy minimal and TypeScript projects can receive a missing tool carrier."""
    desired = (
        '[project]\nname = "demo"\nversion = "0.1.0"\n'
        '\n[dependency-groups]\ndev = ["scaffold-guard>=0.2.0"]\n'
    )

    change = plan_dependency_floor_migration(
        tmp_path,
        desired_content=desired,
        minimum_version="0.2.0",
        allow_create=True,
    )

    assert change is not None
    assert change.kind == "create"
    assert change.content == desired


def test_dependency_floor_migration_refuses_unexpected_missing_pyproject(
    tmp_path: Path,
) -> None:
    """Missing Python or monorepo metadata is treated as drift."""
    with pytest.raises(MigrationError, match="unexpectedly missing"):
        plan_dependency_floor_migration(
            tmp_path,
            desired_content="",
            minimum_version="0.2.0",
            allow_create=False,
        )


def test_dependency_floor_migration_refuses_source_override(tmp_path: Path) -> None:
    """Direct local sources require manual migration."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n'
        '\n[dependency-groups]\ndev = ["scaffold-guard>=0.1.3"]\n'
        '\n[tool.uv.sources]\nscaffold-guard = { path = "../local" }\n',
        encoding="utf-8",
    )

    with pytest.raises(MigrationError, match="sources"):
        plan_dependency_floor_migration(
            tmp_path,
            desired_content="",
            minimum_version="0.2.0",
            allow_create=False,
        )


def test_dependency_floor_migration_refuses_inline_source_override(tmp_path: Path) -> None:
    """Inline uv source tables are rejected like expanded source tables."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n'
        '\n[dependency-groups]\ndev = ["scaffold-guard>=0.1.3"]\n'
        '\n[tool.uv]\nsources = { scaffold-guard = { path = "../local" } }\n',
        encoding="utf-8",
    )

    with pytest.raises(MigrationError, match="sources"):
        plan_dependency_floor_migration(
            tmp_path,
            desired_content="",
            minimum_version="0.2.0",
            allow_create=False,
        )


def test_dependency_floor_migration_refuses_direct_url_requirement(tmp_path: Path) -> None:
    """PEP 508 direct references are preserved for manual resolution."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n'
        "\n[dependency-groups]\ndev = ["
        '"scaffold-guard @ file:///tmp/scaffold-guard"]\n',
        encoding="utf-8",
    )

    with pytest.raises(MigrationError, match="direct URL/path"):
        plan_dependency_floor_migration(
            tmp_path,
            desired_content="",
            minimum_version="0.2.0",
            allow_create=False,
        )


@pytest.mark.parametrize(
    ("requirement", "message"),
    [
        ('"scaffold-guard[dev]>=0.1.3"', "extras"),
        ('"scaffold-guard>=0.1.3; python_version >= \\"3.13\\""', "environment markers"),
        ('"scaffold_guard>=0.1.3"', "custom scaffold-guard requirement name"),
        ('"scaffold-guard==0.1.3"', "custom scaffold-guard version requirement"),
        ('"scaffold-guard>=0.1.0,<1"', "custom scaffold-guard version requirement"),
        ('"scaffold-guard"', "custom scaffold-guard version requirement"),
    ],
)
def test_dependency_floor_migration_refuses_custom_requirement_forms(
    tmp_path: Path,
    requirement: str,
    message: str,
) -> None:
    """Only the generated simple scaffold-guard requirement entry is rewritten."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n'
        f"\n[dependency-groups]\ndev = [{requirement}]\n",
        encoding="utf-8",
    )

    with pytest.raises(MigrationError, match=message):
        plan_dependency_floor_migration(
            tmp_path,
            desired_content="",
            minimum_version="0.2.0",
            allow_create=False,
        )


def test_dependency_floor_migration_rejects_symlink_outside_root(tmp_path: Path) -> None:
    """Dependency migration does not follow pyproject symlinks outside root."""
    outside = tmp_path / "outside"
    project = tmp_path / "project"
    outside.mkdir()
    project.mkdir()
    (outside / "pyproject.toml").write_text(
        '[dependency-groups]\ndev = ["scaffold-guard>=0.1.3"]\n',
        encoding="utf-8",
    )
    (project / "pyproject.toml").symlink_to(outside / "pyproject.toml")

    with pytest.raises(
        MigrationError,
        match="symbolic links are not allowed below the project root",
    ):
        plan_dependency_floor_migration(
            project,
            desired_content="",
            minimum_version="0.2.0",
            allow_create=False,
        )


def test_dependency_floor_migration_rejects_symlink_within_root(tmp_path: Path) -> None:
    """Dependency migration treats an in-root pyproject symlink as a conflict."""
    project = tmp_path / "project"
    project.mkdir()
    target = project / "real-pyproject.toml"
    target.write_text(
        '[dependency-groups]\ndev = ["scaffold-guard>=0.1.3"]\n',
        encoding="utf-8",
    )
    (project / "pyproject.toml").symlink_to(target.name)

    with pytest.raises(
        MigrationError,
        match="symbolic links are not allowed below the project root",
    ):
        plan_dependency_floor_migration(
            project,
            desired_content="",
            minimum_version="0.2.0",
            allow_create=False,
        )


def test_dependency_floor_migration_refuses_duplicates(tmp_path: Path) -> None:
    """Ambiguous duplicate requirements are not guessed at."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n'
        "\n[dependency-groups]\ndev = ["
        '"scaffold-guard>=0.1.0", "scaffold_guard>=0.1.3"]\n',
        encoding="utf-8",
    )

    with pytest.raises(MigrationError, match="duplicate"):
        plan_dependency_floor_migration(
            tmp_path,
            desired_content="",
            minimum_version="0.2.0",
            allow_create=False,
        )


@pytest.mark.parametrize(
    ("pyproject", "message"),
    [
        ('[project]\nname = "demo"\n', "dependency-groups"),
        ('[dependency-groups]\ntest = ["pytest"]\n', "dependency-groups.dev"),
        ('[dependency-groups]\ndev = ["pytest"]\n', "no scaffold-guard"),
    ],
)
def test_dependency_floor_migration_refuses_missing_generated_structure(
    tmp_path: Path,
    pyproject: str,
    message: str,
) -> None:
    """Existing custom projects are not reshaped when generated fields are absent."""
    (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")

    with pytest.raises(MigrationError, match=message):
        plan_dependency_floor_migration(
            tmp_path,
            desired_content="",
            minimum_version="0.2.0",
            allow_create=False,
        )
