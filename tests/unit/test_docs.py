"""Tests for public documentation command and adapter references."""

from pathlib import Path

PUBLIC_INSTALL_DOCS = (
    Path("README.md"),
    Path("docs/index.md"),
    Path("docs/quickstart.md"),
)
CODEX_ADAPTER_DOCS = (
    Path("README.md"),
    Path("docs/adapters.md"),
    Path("docs/generated-project.md"),
)
COMMAND_REFERENCE_DOC = Path("docs/commands.md")
EXPECTED_PROFILE_LAYOUT_COUNT = 4


def test_public_install_docs_use_installed_scaffold_guard_command() -> None:
    """Public install docs should advertise the PyPI tool install flow."""
    for path in PUBLIC_INSTALL_DOCS:
        content = path.read_text(encoding="utf-8")

        assert "uv tool install scaffold-guard" in content
        assert "uvx" not in content

    for path in (Path("docs/index.md"), Path("docs/quickstart.md")):
        content = path.read_text(encoding="utf-8")

        assert "uv run scaffold-guard" not in content

    readme = Path("README.md").read_text(encoding="utf-8")

    assert "uv run scaffold-guard init" not in readme
    assert "uv run scaffold-guard check" not in readme
    assert "uv run scaffold-guard validate" not in readme
    assert "uv run scaffold-guard upgrade" not in readme


def test_codex_adapter_docs_describe_layered_file_responsibilities() -> None:
    """Codex docs should keep behavior, config, policy, and checks separated."""
    expected_phrases = (
        "`AGENTS.md` remains behavioral guidance",
        "`.codex/config.toml` enables Codex features and project-scoped agent defaults",
        "`.codex/agents/*.toml`",
        "`.codex/rules/*.rules` handles command permission policy",
        "`.codex/hooks.json` runs generated hook commands",
        "`.codex/hooks/workflow-evidence.sh`",
        "mechanical workflow evidence and checks",
    )

    for path in CODEX_ADAPTER_DOCS:
        content = " ".join(path.read_text(encoding="utf-8").split())

        for phrase in expected_phrases:
            assert phrase in content


def test_command_reference_documents_user_facing_cli_commands() -> None:
    """The docs should explain the public command surface beyond init."""
    nav_content = Path("mkdocs.yml").read_text(encoding="utf-8")
    command_content = COMMAND_REFERENCE_DOC.read_text(encoding="utf-8")

    assert "Command Reference: commands.md" in nav_content

    expected_phrases = (
        "scaffold-guard check",
        "Run fast local policy checks",
        "scaffold-guard inspect-diff",
        "Report which validation evidence is expected",
        "scaffold-guard validate",
        "Run the validation commands configured",
        "scaffold-guard upgrade",
        "Preview or apply a generated-project upgrade",
        "scaffold-guard publish",
        "Validate, commit, and push",
        "scaffold-guard compile-rules",
        "Regenerate managed agent instruction files",
        "scaffold-guard doctor",
        "Report local environment and generated-project health",
        "scaffold-guard version",
        "Print the installed ScaffoldGuard version",
    )

    for phrase in expected_phrases:
        assert phrase in command_content


def test_upgrade_docs_describe_preview_apply_and_ownership_boundaries() -> None:
    """Upgrade docs should keep the public v0.2.0 safety contract visible."""
    command_content = COMMAND_REFERENCE_DOC.read_text(encoding="utf-8")
    generated_content = Path("docs/generated-project.md").read_text(encoding="utf-8")
    combined = " ".join(f"{command_content}\n{generated_content}".split())

    expected_phrases = (
        "scaffold-guard upgrade [--path .] [--apply] [--json] [--accept-legacy PATH]",
        "Preview is the default and is read-only",
        "explicitly choosing to let ScaffoldGuard write the upgrade",
        "`.scaffold-guard/manifest.json`",
        "managed-file records only",
        "project metadata includes `manifest_version`, `project_format_version`, "
        "`generated_with`, `requires_scaffold_guard`, `profile`, and `adapters`",
        "Each `files` record has exactly `path`, a stable `template_id`, and `sha256`",
        "file records have no lifecycle field",
        "contains exactly `format_version`, `generated_with`, and `requires_scaffold_guard`",
        "Limited to reserved metadata in `scaffold-guard.toml` and the "
        "`scaffold-guard` development requirement or tool-carrier in `pyproject.toml`",
        "never touched by upgrade",
        "exactly `unchanged`, `add`, `update`, `migrate`, `conflict`, and `orphan`, in that order",
        "`applied` is a top-level result boolean",
        "project whose complete managed surface exactly matches a packaged baseline is "
        "adopted without flags",
        "recognized, marker-bearing managed file that differs",
        "Unmarked CI or config files",
        "`orphan` action reports a formerly managed file that remains in place",
        "`1` | Conflicts prevent apply",
        "`2` | Invalid configuration, unsupported version, failed migration, filesystem "
        "failure, or rollback failure",
        "scaffold-guard check",
        "scaffold-guard validate",
    )

    for phrase in expected_phrases:
        assert phrase in combined

    upgrade_section = command_content.split("## `upgrade`", maxsplit=1)[1].split(
        "## `publish`", maxsplit=1
    )[0]
    for obsolete_action_or_status in ("`create`", "`planned`", "`blocked`"):
        assert obsolete_action_or_status not in upgrade_section
    assert "statuses such as" not in upgrade_section


def test_upgrade_repo_local_invocation_stays_in_generated_agent_guidance() -> None:
    """Repo-local upgrade commands should appear only where pinned versions matter."""
    generated_guidance_paths = {
        Path("docs/adapters.md"),
        Path("docs/generated-project.md"),
    }
    public_command_paths = (
        Path("README.md"),
        Path("docs/index.md"),
        Path("docs/quickstart.md"),
        Path("docs/commands.md"),
    )

    for path in public_command_paths:
        content = path.read_text(encoding="utf-8")
        assert "uv run scaffold-guard upgrade" not in content

    for path in generated_guidance_paths:
        content = path.read_text(encoding="utf-8")
        assert "uv run scaffold-guard upgrade" in content

    adapter_content = " ".join(Path("docs/adapters.md").read_text(encoding="utf-8").split())
    assert "for both preview and the audited `--apply` path" in adapter_content
    assert "technical permission does not authorize a write" in adapter_content
    assert "protecting applied upgrades" not in adapter_content


def test_generated_profile_layouts_list_the_tracked_manifest() -> None:
    """Every public profile tree should include the generated manifest."""
    readme = Path("README.md").read_text(encoding="utf-8")
    readme_layouts = readme.split("## Generated Project", maxsplit=1)[1].split(
        "Adapter files are added", maxsplit=1
    )[0]
    generated = Path("docs/generated-project.md").read_text(encoding="utf-8")
    generated_layouts = generated.split("# Generated Project", maxsplit=1)[1].split(
        "## Configuration", maxsplit=1
    )[0]
    manifest_tree_entry = "my_project/\n  .scaffold-guard/manifest.json"

    assert readme_layouts.count(manifest_tree_entry) == EXPECTED_PROFILE_LAYOUT_COUNT
    assert generated_layouts.count(manifest_tree_entry) == EXPECTED_PROFILE_LAYOUT_COUNT


def test_legacy_typescript_manifest_tracking_is_documented() -> None:
    """Legacy seed gitignores should have an explicit manifest tracking recovery."""
    expected_phrases = (
        "Legacy `0.1.x` TypeScript and monorepo projects",
        "user-owned seed `.gitignore`; upgrade does not edit that file",
        "review and remove the old ignore entry",
        "`git add -f .scaffold-guard/manifest.json`",
        "so the manifest is tracked",
    )

    for path in (Path("docs/commands.md"), Path("docs/generated-project.md")):
        content = " ".join(path.read_text(encoding="utf-8").split())

        for phrase in expected_phrases:
            assert phrase in content


def test_release_docs_list_all_version_bump_touchpoints() -> None:
    """The release checklist should keep coordinated version sources together."""
    release_docs = Path("docs/releasing.md").read_text(encoding="utf-8")
    version_bump_list = """   pyproject.toml
   src/scaffold_guard/__init__.py
   tests/integration/test_import_package.py
   uv.lock
   CHANGELOG.md"""

    assert version_bump_list in release_docs


def test_limitations_do_not_claim_upgrade_is_unavailable() -> None:
    """README limitations should keep adoption and Homebrew limits, not upgrade removal."""
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "Homebrew" in readme
    assert "automatic adoption of mature existing repositories" in readme
    assert "automatic upgrades for mature existing repositories" not in readme
