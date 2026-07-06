"""Runner for all V1 generated-project checks."""

from pathlib import Path

from agent_safe.checks.base import CheckConfigurationError, CheckReport
from agent_safe.checks.config_consistency import check_config_consistency
from agent_safe.checks.generated_files import check_generated_files
from agent_safe.checks.project_health import check_project_health
from agent_safe.checks.unsafe_patterns import check_unsafe_patterns


def run_checks(path: Path) -> CheckReport:
    """Run all V1 project policy checks."""
    root = path.resolve(strict=False)
    if not root.exists():
        msg = f"Project path does not exist: {path}"
        raise CheckConfigurationError(msg)
    if not root.is_dir():
        msg = f"Project path is not a directory: {path}"
        raise CheckConfigurationError(msg)

    return CheckReport(
        path=path,
        checks=(
            check_unsafe_patterns(root),
            check_project_health(root),
            check_generated_files(root),
            check_config_consistency(root),
        ),
    )
