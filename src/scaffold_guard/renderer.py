"""Template rendering for generated project files."""

from collections.abc import Mapping

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape


class TemplateRenderer:
    """Render packaged Jinja templates with strict variable checking."""

    def __init__(self) -> None:
        """Create a renderer backed by the package `templates` directory."""
        self._environment = Environment(
            loader=PackageLoader("scaffold_guard", "templates"),
            undefined=StrictUndefined,
            autoescape=select_autoescape(
                enabled_extensions=("html", "xml"),
                default_for_string=False,
                default=False,
            ),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

    def render(self, template_name: str, context: Mapping[str, object]) -> str:
        """Render a packaged template with the given context."""
        template = self._environment.get_template(template_name)
        return template.render(context)
