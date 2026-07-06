"""Module entry point for `python -m agent_safe`."""

from agent_safe.cli import app


def main() -> None:
    """Run the Typer application."""
    app()


if __name__ == "__main__":
    main()
