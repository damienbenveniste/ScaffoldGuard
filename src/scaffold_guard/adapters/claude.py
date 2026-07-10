"""Claude Code adapter support."""

from scaffold_guard.models import TemplateSpec


def _managed_spec(template_name: str, destination: str) -> TemplateSpec:
    """Return a managed Claude adapter template spec."""
    return TemplateSpec(
        template_id=template_name.removesuffix(".j2"),
        template_name=template_name,
        destination=destination,
        lifecycle="managed",
    )


class ClaudeAdapter:
    """Generate Claude Code wrapper and path-scoped rule files."""

    def template_specs(self) -> tuple[TemplateSpec, ...]:
        """Return Claude Code adapter templates."""
        return (
            _managed_spec("agents/claude/CLAUDE.md.j2", "CLAUDE.md"),
            _managed_spec("agents/claude/rules/python.md.j2", ".claude/rules/python.md"),
            _managed_spec("agents/claude/rules/testing.md.j2", ".claude/rules/testing.md"),
            _managed_spec("agents/claude/rules/docs.md.j2", ".claude/rules/docs.md"),
            _managed_spec("agents/claude/rules/security.md.j2", ".claude/rules/security.md"),
            _managed_spec(
                "agents/claude/rules/git-hygiene.md.j2",
                ".claude/rules/git-hygiene.md",
            ),
        )
