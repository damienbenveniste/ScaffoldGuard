"""Codex adapter support."""

from scaffold_guard.models import TemplateSpec


class CodexAdapter:
    """Generate Codex project configuration, rules, and hooks."""

    def template_specs(self) -> tuple[TemplateSpec, ...]:
        """Return Codex adapter templates."""
        return (
            TemplateSpec("agents/codex/config.toml.j2", ".codex/config.toml"),
            TemplateSpec("agents/codex/hooks.json.j2", ".codex/hooks.json"),
            TemplateSpec("agents/codex/rules/git.rules.j2", ".codex/rules/git.rules"),
            TemplateSpec(
                "agents/codex/rules/validation.rules.j2",
                ".codex/rules/validation.rules",
            ),
        )
