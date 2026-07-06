"""Import smoke tests for the package."""

import agent_safe


def test_package_exposes_version() -> None:
    """The package exposes a stable version string."""
    assert agent_safe.__version__ == "0.1.0"
