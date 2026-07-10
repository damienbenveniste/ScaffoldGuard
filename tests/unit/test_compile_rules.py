"""Tests for generated agent rule compilation."""

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from typer.testing import CliRunner

import scaffold_guard.compile_rules as compile_rules_module
from scaffold_guard.cli import app
from scaffold_guard.compile_rules import (
    GENERATED_MARKER,
    compile_rules,
    selected_agent_files,
)
from scaffold_guard.manifest import (
    MANIFEST_RELATIVE_PATH,
    bytes_sha256,
    load_manifest,
    write_manifest,
)
from scaffold_guard.models import AgentChoice, InitOptions, TemplateSpec
from scaffold_guard.project_config import load_generated_project_config
from scaffold_guard.upgrade import UpgradeError, UpgradePlan, plan_upgrade

SUCCESS = 0
CONFIG_ERROR = 2


def _rule_block(rules: str, pattern: str) -> str:
    """Return the generated prefix-rule block for an exact pattern line."""
    start = rules.index(f"    pattern = {pattern},")
    end = rules.index("\n)\n", start)
    return rules[start:end]


def test_compile_rules_is_idempotent_and_reports_selected_files(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Rule compilation can safely refresh generated agent instruction files."""
    project_dir = generated_project(tmp_path)
    agents_path = project_dir / "AGENTS.md"
    initial_content = agents_path.read_text(encoding="utf-8")

    summary = compile_rules(project_dir, agent="all", dry_run=False, force=False)
    second_summary = compile_rules(project_dir, agent="all", dry_run=False, force=False)
    payload = summary.to_json()
    files = cast("list[str]", payload["files"])
    selected_files = selected_agent_files(load_generated_project_config(project_dir))

    assert not summary.dry_run
    assert Path("AGENTS.md") in summary.files
    assert Path("AGENTS.md") in second_summary.files
    assert "AGENTS.md" in files
    assert Path(".codex/config.toml") in selected_files
    assert Path(".codex/hooks.json") in selected_files
    assert Path(".codex/agents/implementation-worker.toml") in selected_files
    assert Path(".codex/agents/docs-worker.toml") in selected_files
    assert Path(".codex/agents/reviewer.toml") in selected_files
    assert Path(".codex/hooks/workflow-evidence.sh") in selected_files
    assert Path(".codex/rules/validation.rules") in selected_files
    assert Path(".cursor/rules/python.mdc") in selected_files
    assert agents_path.read_text(encoding="utf-8") == initial_content
    assert agents_path.read_text(encoding="utf-8").count(GENERATED_MARKER) == 1
    git_rules = (project_dir / ".codex/rules/git.rules").read_text(encoding="utf-8")
    agents_content = agents_path.read_text(encoding="utf-8")
    claude_content = (project_dir / "CLAUDE.md").read_text(encoding="utf-8")
    cursor_git_rules = (project_dir / ".cursor/rules/git-hygiene.mdc").read_text(encoding="utf-8")
    claude_git_rules = (project_dir / ".claude/rules/git-hygiene.md").read_text(encoding="utf-8")

    upgrade_rule = _rule_block(
        git_rules,
        '["uv", "run", "scaffold-guard", "upgrade"]',
    )
    assert 'decision = "allow"' in upgrade_rule
    assert '"uv run scaffold-guard upgrade"' in upgrade_rule
    assert '"uv run scaffold-guard upgrade --apply"' in upgrade_rule
    assert "not_match" not in upgrade_rule
    assert 'pattern = ["uv", "run", "scaffold-guard", "publish"]' in git_rules
    assert 'pattern = ["scaffold-guard", "publish"]' not in git_rules
    assert 'pattern = ["scaffold-guard", "upgrade"]' not in git_rules
    assert 'decision = "prompt"' not in git_rules
    assert "uv run scaffold-guard upgrade` is safe" in agents_content
    assert (
        "Do not run `uv run scaffold-guard upgrade --apply` unless the user explicitly"
        in agents_content
    )
    assert "asks for the apply step" in agents_content
    assert "uv run scaffold-guard upgrade` is safe as a preview" in claude_content
    assert "uv run scaffold-guard upgrade` is safe to run as a preview" in claude_git_rules
    assert "uv run scaffold-guard upgrade` is safe to run as a preview" in cursor_git_rules


def test_compile_rules_renders_upgrade_guidance_for_all_profiles(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Every profile renders the same upgrade boundary and command protections."""
    for profile in ("minimal", "python", "typescript", "monorepo"):
        project_dir = generated_project(tmp_path / profile, profile=profile)
        agents_content = (project_dir / "AGENTS.md").read_text(encoding="utf-8")
        git_rules = (project_dir / ".codex/rules/git.rules").read_text(encoding="utf-8")
        claude_content = (project_dir / "CLAUDE.md").read_text(encoding="utf-8")
        claude_git_rules = (project_dir / ".claude/rules/git-hygiene.md").read_text(
            encoding="utf-8"
        )
        cursor_git_rules = (project_dir / ".cursor/rules/git-hygiene.mdc").read_text(
            encoding="utf-8"
        )
        upgrade_rule = _rule_block(
            git_rules,
            '["uv", "run", "scaffold-guard", "upgrade"]',
        )
        publish_rule = _rule_block(
            git_rules,
            '["uv", "run", "scaffold-guard", "publish"]',
        )

        assert "uv run scaffold-guard upgrade` is safe" in agents_content
        assert "uv run scaffold-guard upgrade --apply` unless the user explicitly" in (
            agents_content
        )
        assert "reviewed the generated upgrade plan" in agents_content
        assert "uv run scaffold-guard upgrade` is safe as a preview" in claude_content
        assert "only after explicit user intent and a reviewed upgrade plan" in claude_content
        assert "uv run scaffold-guard upgrade` is safe to run as a preview" in claude_git_rules
        assert "unless the user explicitly asks for the apply step" in claude_git_rules
        assert "reviewed the generated upgrade plan" in claude_git_rules
        assert "uv run scaffold-guard upgrade` is safe to run as a preview" in cursor_git_rules
        assert "unless the user explicitly asks for the apply step" in cursor_git_rules
        assert "reviewed the generated upgrade plan" in cursor_git_rules
        assert 'decision = "allow"' in upgrade_rule
        assert '"uv run scaffold-guard upgrade"' in upgrade_rule
        assert '"uv run scaffold-guard upgrade --apply"' in upgrade_rule
        assert "not_match" not in upgrade_rule
        assert 'decision = "allow"' in publish_rule
        assert 'pattern = ["scaffold-guard", "upgrade"]' not in git_rules
        assert 'pattern = ["scaffold-guard", "publish"]' not in git_rules

        for forbidden_pattern in (
            '["git", "commit"]',
            '["git", "push"]',
            '["git", "reset", "--hard"]',
            '["git", "clean", "-fdx"]',
            '["rm", "-rf"]',
        ):
            assert 'decision = "forbidden"' in _rule_block(git_rules, forbidden_pattern)


def test_compile_rules_refuses_manual_files_without_force(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Manual instruction files are protected unless the user opts into overwrite."""
    project_dir = generated_project(tmp_path)
    agents_path = project_dir / "AGENTS.md"
    agents_path.write_text("# Manual Rules\n", encoding="utf-8")

    with pytest.raises(UpgradeError, match="without --force"):
        compile_rules(project_dir, agent="codex", dry_run=False, force=False)

    summary = compile_rules(project_dir, agent="codex", dry_run=False, force=True)

    assert summary.files == (
        Path("AGENTS.md"),
        Path(".codex/config.toml"),
        Path(".codex/hooks.json"),
        Path(".codex/agents/implementation-worker.toml"),
        Path(".codex/agents/docs-worker.toml"),
        Path(".codex/agents/reviewer.toml"),
        Path(".codex/hooks/workflow-evidence.sh"),
        Path(".codex/rules/git.rules"),
        Path(".codex/rules/validation.rules"),
    )
    assert GENERATED_MARKER in agents_path.read_text(encoding="utf-8")


def test_compile_rules_refuses_marker_preserving_markdown_edits_without_force(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """A retained generated Markdown marker is not enough to allow overwrite."""
    project_dir = generated_project(tmp_path)
    agents_path = project_dir / "AGENTS.md"
    agents_path.write_text(
        agents_path.read_text(encoding="utf-8").replace(
            "## Project Orientation",
            "## Local Project Orientation",
        ),
        encoding="utf-8",
    )

    with pytest.raises(UpgradeError, match=r"AGENTS\.md"):
        compile_rules(project_dir, agent="codex", dry_run=False, force=False)


def test_compile_rules_refuses_invalid_bytes_with_generated_marker_without_force(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Generated marker bytes do not allow non-UTF-8 content drift."""
    project_dir = generated_project(tmp_path)
    agents_path = project_dir / "AGENTS.md"
    agents_path.write_bytes(agents_path.read_bytes() + b"\xff")

    with pytest.raises(UpgradeError, match=r"AGENTS\.md"):
        compile_rules(project_dir, agent="codex", dry_run=False, force=False)


def test_compile_rules_refuses_json_hooks_edits_with_generated_status_without_force(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """A retained generated JSON status phrase is not enough to allow overwrite."""
    project_dir = generated_project(tmp_path)
    hooks_path = project_dir / ".codex/hooks.json"
    hooks_path.write_text(
        hooks_path.read_text(encoding="utf-8").replace(
            "scaffold-guard generated: checking project policy after file edits",
            "scaffold-guard generated: checking project policy after local edits",
        ),
        encoding="utf-8",
    )

    with pytest.raises(UpgradeError, match=r"\.codex/hooks\.json"):
        compile_rules(project_dir, agent="codex", dry_run=False, force=False)


def test_compile_rules_allows_exact_existing_content_without_force(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Exactly rendered files remain idempotent without requiring --force."""
    project_dir = generated_project(tmp_path)
    selected_files = selected_agent_files(load_generated_project_config(project_dir))
    initial_contents = {
        path: (project_dir / path).read_text(encoding="utf-8") for path in selected_files
    }

    summary = compile_rules(project_dir, agent="all", dry_run=False, force=False)

    assert summary.files == selected_files
    assert {
        path: (project_dir / path).read_text(encoding="utf-8") for path in selected_files
    } == initial_contents


def test_compile_rules_force_replaces_changed_generated_content(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """--force preserves the explicit replacement path for changed generated files."""
    project_dir = generated_project(tmp_path)
    agents_path = project_dir / "AGENTS.md"
    expected_content = agents_path.read_text(encoding="utf-8")
    agents_path.write_text(
        expected_content.replace("## Project Orientation", "## Local Project Orientation"),
        encoding="utf-8",
    )

    summary = compile_rules(project_dir, agent="codex", dry_run=False, force=True)

    assert Path("AGENTS.md") in summary.files
    assert agents_path.read_text(encoding="utf-8") == expected_content


def test_compile_rules_rejects_unconfigured_explicit_adapter(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """An explicit adapter is a scope within configured adapters, not an add request."""
    project_dir = generated_project(tmp_path, agent="codex")

    with pytest.raises(UpgradeError, match=r"not enabled.*claude"):
        compile_rules(project_dir, agent="claude", dry_run=True, force=False)

    assert not (project_dir / "CLAUDE.md").exists()


def test_compile_rules_selects_typescript_adapter_files(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """TypeScript projects regenerate TypeScript adapter rules without Python rules."""
    project_dir = generated_project(tmp_path, profile="typescript")
    selected_files = selected_agent_files(load_generated_project_config(project_dir))

    assert Path(".claude/rules/typescript.md") in selected_files
    assert Path(".cursor/rules/typescript.mdc") in selected_files
    assert Path(".claude/rules/python.md") not in selected_files
    assert Path(".cursor/rules/python.mdc") not in selected_files


@pytest.mark.parametrize(
    ("agent", "expected_path"),
    [("claude", Path("CLAUDE.md")), ("cursor", Path(".cursor/rules/testing.mdc"))],
)
def test_compile_rules_explicit_single_adapter_scopes(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    agent: AgentChoice,
    expected_path: Path,
) -> None:
    """Configured Claude and Cursor requests use their exact single-adapter render scope."""
    project_dir = generated_project(tmp_path)

    summary = compile_rules(
        project_dir,
        agent=agent,
        dry_run=True,
        force=False,
    )

    assert expected_path in summary.files


def test_selected_agent_files_uses_lifecycle_and_path_family(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Agent selection includes new managed family paths without admitting managed CI."""
    project_dir = generated_project(tmp_path)

    def fake_package_template_specs(options: InitOptions) -> tuple[TemplateSpec, ...]:
        assert options.agent == "all"
        return (
            TemplateSpec(
                template_id="agents/shared",
                template_name="agents/shared.j2",
                destination="AGENTS.md",
                lifecycle="managed",
            ),
            TemplateSpec(
                template_id="agents/codex/future",
                template_name="agents/codex/future.j2",
                destination=".codex/rules/future.rules",
                lifecycle="managed",
            ),
            TemplateSpec(
                template_id="ci/github",
                template_name="ci/github.j2",
                destination=".github/workflows/ci.yml",
                lifecycle="managed",
            ),
            TemplateSpec(
                template_id="agents/codex/user-owned",
                template_name="agents/codex/user-owned.j2",
                destination=".codex/rules/user-owned.rules",
                lifecycle="seed",
            ),
        )

    monkeypatch.setattr(
        compile_rules_module,
        "package_template_specs",
        fake_package_template_specs,
    )

    selected = selected_agent_files(load_generated_project_config(project_dir))

    assert selected == (Path("AGENTS.md"), Path(".codex/rules/future.rules"))


def test_compile_rules_force_updates_manifest_hashes(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Forced reconciliation writes rendered bytes and records their exact new hashes."""
    project_dir = generated_project(tmp_path)
    config_path = project_dir / "scaffold-guard.toml"
    config_text = config_path.read_text(encoding="utf-8")
    config_path.write_text(
        config_text.replace("ruff = true", "ruff = false").replace(
            'ruff_mode = "strict"',
            'ruff_mode = "off"',
        ),
        encoding="utf-8",
    )
    before = load_manifest(project_dir / MANIFEST_RELATIVE_PATH)
    before_hash = next(file.sha256 for file in before.files if file.path == "AGENTS.md")

    compile_rules(project_dir, agent="codex", dry_run=False, force=True)

    after = load_manifest(project_dir / MANIFEST_RELATIVE_PATH)
    after_hash = next(file.sha256 for file in after.files if file.path == "AGENTS.md")
    assert after_hash == bytes_sha256((project_dir / "AGENTS.md").read_bytes())
    assert after_hash != before_hash


def test_compile_rules_scoped_plan_preserves_nonselected_manifest_records(
    tmp_path: Path,
    generated_project: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A scoped compile updates selected hashes without orphaning other adapters."""
    project_dir = generated_project(tmp_path)
    config_path = project_dir / "scaffold-guard.toml"
    config_text = config_path.read_text(encoding="utf-8")
    config_path.write_text(
        config_text.replace("ruff = true", "ruff = false").replace(
            'ruff_mode = "strict"',
            'ruff_mode = "off"',
        ),
        encoding="utf-8",
    )
    before = load_manifest(project_dir / MANIFEST_RELATIVE_PATH)
    before_nonselected = {
        file.path: file
        for file in before.files
        if file.path == "CLAUDE.md" or file.path.startswith((".claude/", ".cursor/"))
    }
    captured: list[UpgradePlan] = []
    real_plan_upgrade = plan_upgrade

    def capture_plan(
        root: Path,
        *,
        accept_legacy: tuple[Path, ...] = (),
        paths: tuple[Path, ...] | None = None,
        force: bool = False,
        include_migrations: bool = True,
    ) -> UpgradePlan:
        plan = real_plan_upgrade(
            root,
            accept_legacy=accept_legacy,
            paths=paths,
            force=force,
            include_migrations=include_migrations,
        )
        captured.append(plan)
        return plan

    monkeypatch.setattr(compile_rules_module, "plan_upgrade", capture_plan)

    compile_rules(project_dir, agent="codex", dry_run=False, force=False)

    after = load_manifest(project_dir / MANIFEST_RELATIVE_PATH)
    after_by_path = {file.path: file for file in after.files}
    assert captured
    assert not any(action.kind == "orphan" for action in captured[0].actions)
    assert {path: after_by_path[path] for path in before_nonselected} == before_nonselected


def test_compile_rules_omitted_agent_preserves_empty_configured_set(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Omitted --agent compiles shared instructions even when no adapter is enabled."""
    project_dir = generated_project(tmp_path)
    config_path = project_dir / "scaffold-guard.toml"
    config_text = config_path.read_text(encoding="utf-8")
    for adapter in ("codex", "claude", "cursor"):
        config_text = config_text.replace(f"{adapter} = true", f"{adapter} = false")
    config_path.write_text(config_text, encoding="utf-8")
    manifest_path = project_dir / MANIFEST_RELATIVE_PATH
    manifest = load_manifest(manifest_path)
    write_manifest(manifest_path, replace(manifest, adapters=()))

    summary = compile_rules(project_dir, agent=None, dry_run=False, force=False)

    assert summary.files == (Path("AGENTS.md"),)


def test_compile_rules_requires_legacy_upgrade_first(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """Manifest-less projects receive explicit upgrade-first guidance."""
    project_dir = generated_project(tmp_path)
    (project_dir / MANIFEST_RELATIVE_PATH).unlink()

    with pytest.raises(UpgradeError, match=r"scaffold-guard upgrade.*first"):
        compile_rules(project_dir, agent=None, dry_run=False, force=False)


def test_compile_rules_requires_version_upgrade_before_newer_templates(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """A newer runtime cannot update managed files without structured metadata migration."""
    project_dir = generated_project(tmp_path)
    config_path = project_dir / "scaffold-guard.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            'generated_with = "0.2.0"',
            'generated_with = "0.1.5"',
        ),
        encoding="utf-8",
    )
    manifest_path = project_dir / MANIFEST_RELATIVE_PATH
    manifest = load_manifest(manifest_path)
    write_manifest(manifest_path, replace(manifest, generated_with="0.1.5"))

    with pytest.raises(UpgradeError, match=r"preview and apply.*upgrade.*first"):
        compile_rules(project_dir, agent=None, dry_run=False, force=False)


def test_compile_rules_cli_dry_run_leaves_files_unchanged(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """The public compile-rules dry-run path reports planned writes only."""
    project_dir = generated_project(tmp_path)
    agents_path = project_dir / "AGENTS.md"
    agents_path.write_text("# Manual Rules\n", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "compile-rules",
            "--path",
            str(project_dir),
            "--agent",
            "codex",
            "--dry-run",
            "--force",
        ],
    )

    assert result.exit_code == SUCCESS, result.output
    assert "Planned agent instruction files" in result.output
    assert agents_path.read_text(encoding="utf-8") == "# Manual Rules\n"


def test_compile_rules_cli_reports_configuration_errors(tmp_path: Path) -> None:
    """The public compile-rules command reports missing generated config distinctly."""
    result = CliRunner().invoke(app, ["compile-rules", "--path", str(tmp_path)])

    assert result.exit_code == CONFIG_ERROR
    assert "Generated project config is missing" in result.output


def test_compile_rules_cli_reports_upgrade_errors(
    tmp_path: Path,
    generated_project: Callable[..., Path],
) -> None:
    """The CLI catches planner errors such as an unconfigured adapter scope."""
    project_dir = generated_project(tmp_path, agent="codex")

    result = CliRunner().invoke(
        app,
        ["compile-rules", "--path", str(project_dir), "--agent", "claude"],
    )

    assert result.exit_code == CONFIG_ERROR
    assert "Requested adapters are not enabled" in result.output
