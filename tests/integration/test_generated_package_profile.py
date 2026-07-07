"""Integration tests for `scaffold-guard init` package generation."""

import importlib
import json
import py_compile
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Protocol, cast

import pytest
from typer.testing import CliRunner

from scaffold_guard.cli import app

SUCCESS = 0
CONFIG_ERROR = 2

BASE_PACKAGE_FILES = {
    Path("AGENTS.md"),
    Path("README.md"),
    Path("LICENSE"),
    Path("pyproject.toml"),
    Path("pyrightconfig.json"),
    Path(".gitignore"),
    Path(".github/workflows/ci.yml"),
    Path(".github/workflows/docs.yml"),
    Path("docs/index.md"),
    Path("examples/hello.py"),
    Path("src/demo/__init__.py"),
    Path("src/demo/py.typed"),
    Path("src/demo/core.py"),
    Path("tests/unit/test_core.py"),
    Path("tests/integration/test_import_package.py"),
    Path("scaffold-guard.toml"),
}


class GreetingPackage(Protocol):
    """Imported generated package surface used by the smoke test."""

    def greet(self, name: str = "World") -> str:
        """Return a generated greeting."""
        ...


def test_init_codex_generates_valid_package_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The codex adapter creates a base package tree with only AGENTS.md."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["init", "demo", "--agent", "codex"])

    assert result.exit_code == SUCCESS, result.output
    project_dir = tmp_path / "demo"
    assert _relative_files(project_dir) == BASE_PACKAGE_FILES
    assert not (project_dir / "CLAUDE.md").exists()
    assert not (project_dir / ".claude").exists()
    assert not (project_dir / ".cursor").exists()
    assert "Created ScaffoldGuard Python project: demo" in result.output
    assert "Codex: AGENTS.md" in result.output

    _assert_no_unresolved_project_placeholders(project_dir)
    _assert_python_files_compile(project_dir)
    with _import_from_project(project_dir):
        package = cast(GreetingPackage, importlib.import_module("demo"))
        assert package.greet("Codex") == "Hello, Codex!"


def test_check_passes_in_fresh_generated_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A freshly generated all-adapter project passes `scaffold-guard check`."""
    monkeypatch.chdir(tmp_path)
    init_result = CliRunner().invoke(app, ["init", "demo"])

    assert init_result.exit_code == SUCCESS, init_result.output

    check_result = CliRunner().invoke(app, ["check", "--path", "demo"])

    assert check_result.exit_code == SUCCESS, check_result.output
    assert "scaffold-guard check: ok" in check_result.output
    assert "- unsafe-patterns: ok" in check_result.output


def test_check_text_output_reports_failure_locations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Text mode lists findings with path and line number."""
    monkeypatch.chdir(tmp_path)
    init_result = CliRunner().invoke(app, ["init", "demo", "--agent", "codex"])
    assert init_result.exit_code == SUCCESS, init_result.output
    core_path = tmp_path / "demo/src/demo/core.py"
    core_path.write_text(core_path.read_text(encoding="utf-8") + "\nvalue = 1  # type: ignore\n")

    check_result = CliRunner().invoke(app, ["check", "--path", "demo"])

    assert check_result.exit_code == 1
    assert "scaffold-guard check: failed" in check_result.output
    assert "src/demo/core.py:" in check_result.output
    assert "no-type-ignore" in check_result.output


def test_check_invalid_path_uses_configuration_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid check targets use exit code 2."""
    monkeypatch.chdir(tmp_path)

    check_result = CliRunner().invoke(app, ["check", "--path", "missing"])

    assert check_result.exit_code == CONFIG_ERROR
    assert "Project path does not exist" in check_result.output


def test_check_json_output_is_parseable_for_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JSON mode emits the documented report shape."""
    monkeypatch.chdir(tmp_path)
    init_result = CliRunner().invoke(app, ["init", "demo", "--agent", "codex"])
    assert init_result.exit_code == SUCCESS, init_result.output
    agents_path = tmp_path / "demo/AGENTS.md"
    agents_path.unlink()

    check_result = CliRunner().invoke(app, ["check", "--path", "demo", "--json"])

    assert check_result.exit_code == 1
    payload = cast("dict[str, object]", json.loads(check_result.output))
    checks = cast("list[dict[str, object]]", payload["checks"])
    assert payload["ok"] is False
    assert any(check["id"] == "project-health" and check["ok"] is False for check in checks)


def test_init_all_generates_all_adapter_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default all-adapter path creates Claude and Cursor files."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["init", "demo"])

    assert result.exit_code == SUCCESS, result.output
    project_dir = tmp_path / "demo"
    files = _relative_files(project_dir)
    assert BASE_PACKAGE_FILES.issubset(files)
    assert Path("CLAUDE.md") in files
    assert Path(".claude/rules/python.md") in files
    assert Path(".cursor/rules/python.mdc") in files
    assert "@AGENTS.md" in (project_dir / "CLAUDE.md").read_text(encoding="utf-8")
    assert "alwaysApply: false" in (project_dir / ".cursor/rules/python.mdc").read_text(
        encoding="utf-8"
    )
    assert "Claude Code: CLAUDE.md + .claude/rules/" in result.output
    assert "Cursor: .cursor/rules/*.mdc + AGENTS.md" in result.output


def test_init_without_name_runs_guided_setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Omitting NAME starts guided setup and uses prompted values."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["init"],
        input="guided-demo\nclaude\n\nApache-2.0\n3.14\n90\n\n",
    )

    assert result.exit_code == SUCCESS, result.output
    project_dir = tmp_path / "guided-demo"
    assert (project_dir / "CLAUDE.md").exists()
    assert not (project_dir / ".cursor").exists()
    pyproject = (project_dir / "pyproject.toml").read_text(encoding="utf-8")
    config = (project_dir / "scaffold-guard.toml").read_text(encoding="utf-8")
    assert 'requires-python = ">=3.14"' in pyproject
    assert "fail_under = 90" in pyproject
    assert 'license = "Apache-2.0"' in pyproject
    assert 'python_min = "3.14"' in config
    assert "coverage_fail_under = 90" in config
    assert "ScaffoldGuard guided setup" in result.output
    assert "Created ScaffoldGuard Python project: guided-demo" in result.output


def test_init_guided_recovers_from_invalid_prompt_answers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guided setup reports invalid choices and asks again."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["init"],
        input="demo\nbad-agent\ncodex\npackage\nMIT\n3.13\nnot-a-number\n101\n95\ngithub\n",
    )

    assert result.exit_code == SUCCESS, result.output
    assert (tmp_path / "demo/AGENTS.md").exists()
    assert not (tmp_path / "demo/CLAUDE.md").exists()
    assert "Choose one of: codex, claude, cursor, all" in result.output
    assert "Coverage floor must be an integer." in result.output
    assert "Coverage floor must be between 1 and 100." in result.output


def test_init_dot_with_explicit_options_generates_project_in_current_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit options keep current-directory init non-interactive."""
    project_dir = tmp_path / "already-created"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)

    result = CliRunner().invoke(app, ["init", ".", "--agent", "codex"])

    assert result.exit_code == SUCCESS, result.output
    assert (project_dir / "AGENTS.md").exists()
    assert (project_dir / "src/already_created/core.py").exists()
    assert not (project_dir / "already-created").exists()
    assert "ScaffoldGuard guided setup" not in result.output
    assert "Created ScaffoldGuard Python project: already-created" in result.output
    assert "  cd already-created" not in result.output


def test_init_dot_without_explicit_options_runs_guided_setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bare `init .` starts guided setup in an existing empty current directory."""
    project_dir = tmp_path / "guided-dot"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)

    result = CliRunner().invoke(app, ["init", "."], input="\ncodex\n\n\n\n\n\n")

    assert result.exit_code == SUCCESS, result.output
    assert (project_dir / "AGENTS.md").exists()
    assert (project_dir / "src/guided_dot/core.py").exists()
    assert not (project_dir / ".cursor").exists()
    assert "ScaffoldGuard guided setup" in result.output
    assert "Created ScaffoldGuard Python project: guided-dot" in result.output
    assert "  cd guided-dot" not in result.output


def test_init_guided_accepts_dot_for_current_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guided setup accepts dot as the current-directory target."""
    project_dir = tmp_path / "guided-current"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)

    result = CliRunner().invoke(app, ["init"], input=".\ncodex\n\n\n\n\n\n")

    assert result.exit_code == SUCCESS, result.output
    assert (project_dir / "AGENTS.md").exists()
    assert (project_dir / "src/guided_current/core.py").exists()
    assert "Created ScaffoldGuard Python project: guided-current" in result.output


def test_init_dry_run_creates_no_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dry-run reports planned files but leaves the target absent."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["init", "demo", "--agent", "codex", "--dry-run"])

    assert result.exit_code == SUCCESS, result.output
    assert "Planned ScaffoldGuard Python project: demo" in result.output
    assert "AGENTS.md" in result.output
    assert not (tmp_path / "demo").exists()


def test_init_rejects_non_empty_existing_directory_without_force(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Populated target directories require explicit force."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo/notes.txt").write_text("keep\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["init", "demo", "--agent", "codex"])

    assert result.exit_code != SUCCESS
    assert "Target directory already exists and is not empty" in result.output


def test_init_force_overwrites_generated_files_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Forced init overwrites planned files and preserves unrelated files."""
    monkeypatch.chdir(tmp_path)
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    (project_dir / "README.md").write_text("old\n", encoding="utf-8")
    (project_dir / "notes.txt").write_text("keep\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["init", "demo", "--agent", "codex", "--force"])

    assert result.exit_code == SUCCESS, result.output
    readme = (project_dir / "README.md").read_text(encoding="utf-8")
    assert "Generated by `scaffold-guard`" in readme
    assert (project_dir / "notes.txt").read_text(encoding="utf-8") == "keep\n"


@pytest.mark.parametrize("name", ["../escape", "bad-name!", "123demo"])
def test_init_rejects_invalid_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    """Unsafe or invalid package names fail before scaffold writes."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["init", name, "--agent", "codex"])

    assert result.exit_code != SUCCESS
    assert not any(tmp_path.iterdir())


def _relative_files(project_dir: Path) -> set[Path]:
    """Return relative files generated below a project directory."""
    return {path.relative_to(project_dir) for path in project_dir.rglob("*") if path.is_file()}


def _assert_no_unresolved_project_placeholders(project_dir: Path) -> None:
    """Fail if project-specific Jinja placeholders remain in generated files."""
    for path in _relative_files(project_dir):
        text = (project_dir / path).read_text(encoding="utf-8")
        assert "{{ project_" not in text
        assert "{{ package_" not in text
        assert "{{ coverage" not in text
        assert "{%" not in text


def _assert_python_files_compile(project_dir: Path) -> None:
    """Compile generated Python files without importing test modules."""
    for path in (project_dir / "src").rglob("*.py"):
        py_compile.compile(str(path), doraise=True)
    for path in (project_dir / "tests").rglob("*.py"):
        py_compile.compile(str(path), doraise=True)
    for path in (project_dir / "examples").rglob("*.py"):
        py_compile.compile(str(path), doraise=True)


@contextmanager
def _import_from_project(project_dir: Path) -> Generator[None]:
    """Temporarily import generated package source from a project directory."""
    src_path = str(project_dir / "src")
    sys.path.insert(0, src_path)
    try:
        yield
    finally:
        sys.path.remove(src_path)
        module = sys.modules.pop("demo", None)
        if isinstance(module, ModuleType):
            importlib.invalidate_caches()
