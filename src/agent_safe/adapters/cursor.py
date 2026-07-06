"""Cursor adapter support."""

from agent_safe.models import TemplateSpec


class CursorAdapter:
    """Generate Cursor project rule files."""

    def template_specs(self) -> tuple[TemplateSpec, ...]:
        """Return Cursor `.mdc` rule templates."""
        return (
            TemplateSpec("agents/cursor/rules/python.mdc.j2", ".cursor/rules/python.mdc"),
            TemplateSpec("agents/cursor/rules/testing.mdc.j2", ".cursor/rules/testing.mdc"),
            TemplateSpec("agents/cursor/rules/docs.mdc.j2", ".cursor/rules/docs.mdc"),
            TemplateSpec("agents/cursor/rules/security.mdc.j2", ".cursor/rules/security.mdc"),
            TemplateSpec(
                "agents/cursor/rules/git-hygiene.mdc.j2",
                ".cursor/rules/git-hygiene.mdc",
            ),
        )
