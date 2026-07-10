"""Codex adapter support."""

from scaffold_guard.models import TemplateSpec


def _managed_spec(template_name: str, destination: str) -> TemplateSpec:
    """Return a managed Codex adapter template spec."""
    return TemplateSpec(
        template_id=template_name.removesuffix(".j2"),
        template_name=template_name,
        destination=destination,
        lifecycle="managed",
    )


class CodexAdapter:
    """Generate Codex project configuration, rules, and hooks."""

    def template_specs(self) -> tuple[TemplateSpec, ...]:
        """Return Codex adapter templates."""
        return (
            _managed_spec("agents/codex/config.toml.j2", ".codex/config.toml"),
            _managed_spec("agents/codex/hooks.json.j2", ".codex/hooks.json"),
            _managed_spec(
                "agents/codex/agents/implementation-worker.toml.j2",
                ".codex/agents/implementation-worker.toml",
            ),
            _managed_spec(
                "agents/codex/agents/docs-worker.toml.j2",
                ".codex/agents/docs-worker.toml",
            ),
            _managed_spec(
                "agents/codex/agents/reviewer.toml.j2",
                ".codex/agents/reviewer.toml",
            ),
            _managed_spec(
                "agents/codex/hooks/workflow-evidence.sh.j2",
                ".codex/hooks/workflow-evidence.sh",
            ),
            _managed_spec("agents/codex/rules/git.rules.j2", ".codex/rules/git.rules"),
            _managed_spec(
                "agents/codex/rules/validation.rules.j2",
                ".codex/rules/validation.rules",
            ),
        )
