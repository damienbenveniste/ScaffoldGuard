"""Codex adapter support."""

from agent_safe.models import TemplateSpec


class CodexAdapter:
    """Codex uses the shared root AGENTS.md file."""

    def template_specs(self) -> tuple[TemplateSpec, ...]:
        """Return no extra templates because AGENTS.md is part of the base profile."""
        return ()
