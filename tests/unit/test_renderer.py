"""Tests for packaged template rendering."""

import pytest
from jinja2 import UndefinedError

from agent_safe.renderer import TemplateRenderer


def test_renderer_loads_packaged_template() -> None:
    """Packaged templates render through the default renderer."""
    rendered = TemplateRenderer().render(
        "package/README.md.j2",
        {"project_slug": "demo-project", "package_name": "demo_project"},
    )

    assert "# demo-project\n" in rendered
    assert "`src/demo_project/` contains package source" in rendered


def test_renderer_fails_on_missing_variables() -> None:
    """StrictUndefined turns incomplete render context into a hard failure."""
    renderer = TemplateRenderer()

    with pytest.raises(UndefinedError):
        renderer.render("package/README.md.j2", {"project_slug": "demo-project"})
