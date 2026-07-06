"""Claude Code adapter support."""

from agent_safe.models import TemplateSpec


class ClaudeAdapter:
    """Generate Claude Code wrapper and path-scoped rule files."""

    def template_specs(self) -> tuple[TemplateSpec, ...]:
        """Return Claude Code adapter templates."""
        return (
            TemplateSpec("agents/claude/CLAUDE.md.j2", "CLAUDE.md"),
            TemplateSpec("agents/claude/rules/python.md.j2", ".claude/rules/python.md"),
            TemplateSpec("agents/claude/rules/testing.md.j2", ".claude/rules/testing.md"),
            TemplateSpec("agents/claude/rules/docs.md.j2", ".claude/rules/docs.md"),
            TemplateSpec("agents/claude/rules/security.md.j2", ".claude/rules/security.md"),
            TemplateSpec(
                "agents/claude/rules/git-hygiene.md.j2",
                ".claude/rules/git-hygiene.md",
            ),
        )
