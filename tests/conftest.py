"""Shared pytest fixtures."""

from collections.abc import Callable
from pathlib import Path

import pytest

from scaffold_guard.models import AgentChoice, ProfileChoice
from scaffold_guard.scaffold import build_init_options, scaffold_package_project, with_quality_tools


@pytest.fixture
def generated_project() -> Callable[..., Path]:
    """Return a factory for generated project fixtures."""

    def create(
        tmp_path: Path,
        *,
        agent: AgentChoice = "all",
        profile: ProfileChoice = "package",
        ruff: bool = True,
        mypy: bool = True,
        pyright: bool = True,
    ) -> Path:
        options = build_init_options(
            "demo",
            base_dir=tmp_path,
            agent=agent,
            profile=profile,
            license_name="MIT",
            python_min="3.13",
            coverage=95,
            ci="github",
            dry_run=False,
            force=False,
        )
        options = with_quality_tools(options, ruff=ruff, mypy=mypy, pyright=pyright)
        scaffold_package_project(options)
        return tmp_path / "demo"

    return create


@pytest.fixture
def replace_text() -> Callable[[Path, str, str], None]:
    """Return a helper that replaces text in a UTF-8 file."""

    def replace(path: Path, old: str, new: str) -> None:
        path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")

    return replace
