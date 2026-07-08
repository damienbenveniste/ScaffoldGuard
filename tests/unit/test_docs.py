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


def test_public_install_docs_use_installed_scaffold_guard_command() -> None:
    """Public install docs should advertise the PyPI tool install flow."""
    for path in PUBLIC_INSTALL_DOCS:
        content = path.read_text(encoding="utf-8")

        assert "uv tool install scaffold-guard" in content
        assert "uvx" not in content
        assert "uv run scaffold-guard" not in content


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
