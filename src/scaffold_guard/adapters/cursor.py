"""Cursor adapter support."""

from scaffold_guard.models import TemplateSpec


def _managed_spec(template_name: str, destination: str) -> TemplateSpec:
    """Return a managed Cursor adapter template spec."""
    return TemplateSpec(
        template_id=template_name.removesuffix(".j2"),
        template_name=template_name,
        destination=destination,
        lifecycle="managed",
    )


class CursorAdapter:
    """Generate Cursor project rule files."""

    def template_specs(self) -> tuple[TemplateSpec, ...]:
        """Return Cursor `.mdc` rule templates."""
        return (
            _managed_spec("agents/cursor/rules/python.mdc.j2", ".cursor/rules/python.mdc"),
            _managed_spec("agents/cursor/rules/testing.mdc.j2", ".cursor/rules/testing.mdc"),
            _managed_spec("agents/cursor/rules/docs.mdc.j2", ".cursor/rules/docs.mdc"),
            _managed_spec("agents/cursor/rules/security.mdc.j2", ".cursor/rules/security.mdc"),
            _managed_spec(
                "agents/cursor/rules/git-hygiene.mdc.j2",
                ".cursor/rules/git-hygiene.mdc",
            ),
        )
