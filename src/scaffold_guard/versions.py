"""Version contracts used by generated projects."""

from typing import Final

from packaging.version import Version

PUBLISH_CAPABLE_MINIMUM_VERSION: Final[str] = "0.1.3"
MANAGED_PROJECT_MINIMUM_VERSION: Final[str] = "0.2.0"
GENERATED_PROJECT_MINIMUM_VERSION: Final[str] = str(
    max(
        Version(PUBLISH_CAPABLE_MINIMUM_VERSION),
        Version(MANAGED_PROJECT_MINIMUM_VERSION),
    )
)
PROJECT_FORMAT_VERSION: Final[int] = 1
MANIFEST_VERSION: Final[int] = 1
PROJECT_METADATA_KEYS: Final[frozenset[str]] = frozenset(
    ("format_version", "generated_with", "requires_scaffold_guard")
)
