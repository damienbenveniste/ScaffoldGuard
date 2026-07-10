"""Import smoke tests for the package."""

import scaffold_guard


def test_package_exposes_version() -> None:
    """The package exposes a stable version string."""
    assert scaffold_guard.__version__ == "0.1.5"
