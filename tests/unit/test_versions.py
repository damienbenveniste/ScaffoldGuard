"""Tests for generated-project feature version contracts."""

from packaging.version import Version

from scaffold_guard.versions import (
    GENERATED_PROJECT_MINIMUM_VERSION,
    MANAGED_PROJECT_MINIMUM_VERSION,
    PUBLISH_CAPABLE_MINIMUM_VERSION,
)


def test_generated_project_minimum_uses_highest_feature_floor() -> None:
    """New generated projects satisfy every command contract they document."""
    assert PUBLISH_CAPABLE_MINIMUM_VERSION == "0.1.3"
    assert MANAGED_PROJECT_MINIMUM_VERSION == "0.2.0"
    assert Version(GENERATED_PROJECT_MINIMUM_VERSION) == max(
        Version(PUBLISH_CAPABLE_MINIMUM_VERSION),
        Version(MANAGED_PROJECT_MINIMUM_VERSION),
    )
