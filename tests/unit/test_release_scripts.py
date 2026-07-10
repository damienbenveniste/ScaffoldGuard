"""Tests for release helper scripts."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from zipfile import ZipFile

REPO_ROOT = Path(__file__).resolve().parents[2]
INSPECT_WHEEL = REPO_ROOT / "scripts" / "inspect-wheel.py"
SMOKE_GENERATED_PROJECT = REPO_ROOT / "scripts" / "smoke-generated-project.sh"


def load_inspect_wheel() -> ModuleType:
    """Load the wheel inspection helper as a testable module."""
    spec = importlib.util.spec_from_file_location("inspect_wheel", INSPECT_WHEEL)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_wheel(path: Path, members: set[str]) -> None:
    """Write a minimal wheel-like zip archive with the requested members."""
    with ZipFile(path, "w") as archive:
        for member in sorted(members):
            archive.writestr(member, "")


def test_inspect_wheel_requires_every_template_under_source_tree(tmp_path: Path) -> None:
    """Template discovery includes current and historical nested templates."""
    inspect_wheel = load_inspect_wheel()
    template_root = tmp_path / "templates"
    (template_root / "minimal").mkdir(parents=True)
    (template_root / "legacy" / "v0_1_5" / "agents" / "codex").mkdir(parents=True)
    (template_root / "minimal" / "AGENTS.md.j2").write_text("", encoding="utf-8")
    (template_root / "legacy" / "v0_1_5" / "agents" / "codex" / "config.toml.j2").write_text(
        "",
        encoding="utf-8",
    )

    required = inspect_wheel.required_members(template_root)

    assert "scaffold_guard/templates/minimal/AGENTS.md.j2" in required
    assert "scaffold_guard/templates/legacy/v0_1_5/agents/codex/config.toml.j2" in required


def test_inspect_wheel_reports_missing_template_and_lifecycle_member(tmp_path: Path) -> None:
    """A wheel missing any discovered template or lifecycle runtime file fails."""
    inspect_wheel = load_inspect_wheel()
    template_root = tmp_path / "templates"
    (template_root / "package").mkdir(parents=True)
    (template_root / "package" / "AGENTS.md.j2").write_text("", encoding="utf-8")

    wheel = tmp_path / "scaffold_guard-0.2.0-py3-none-any.whl"
    write_wheel(wheel, {"scaffold_guard/legacy.py"})

    missing = inspect_wheel.required_members(template_root).difference(
        inspect_wheel.wheel_members(wheel),
    )

    assert "scaffold_guard/templates/package/AGENTS.md.j2" in missing
    assert "scaffold_guard/py.typed" in missing
    assert "scaffold_guard/upgrade.py" in missing


def test_smoke_generated_project_script_uses_exact_built_wheel() -> None:
    """The smoke script prevents generated commands from resolving a newer index build."""
    script = SMOKE_GENERATED_PROJECT.read_text(encoding="utf-8")

    assert 'export UV_FIND_LINKS="${wheelhouse}${UV_FIND_LINKS:+ ${UV_FIND_LINKS}}"' in script
    assert (
        'uv pip install --python .venv/bin/python --reinstall --no-deps "${wheel_file}"' in script
    )
    assert "uv run --no-sync scaffold-guard upgrade" in script
    assert "uv run --no-sync scaffold-guard validate" in script
    assert "direct_url.json" in script
    assert "actual != expected" in script
