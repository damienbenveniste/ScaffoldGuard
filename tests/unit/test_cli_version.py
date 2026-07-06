"""Tests for basic command line entry points."""

from typer.testing import CliRunner

from agent_safe import __version__
from agent_safe.cli import app

SUCCESS = 0


def test_version_command_prints_package_version() -> None:
    """The V1 bootstrap command exposes the package version."""
    result = CliRunner().invoke(app, ["version"])

    assert result.exit_code == SUCCESS
    assert result.stdout == f"{__version__}\n"
