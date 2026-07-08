"""Integration tests for `scaffold-guard init` package generation."""

import importlib
import json
import py_compile
import sys
import tomllib
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
FULL_COVERAGE = 100

CODEX_ADAPTER_FILES = {
    Path(".codex/config.toml"),
    Path(".codex/hooks.json"),
    Path(".codex/agents/implementation-worker.toml"),
    Path(".codex/agents/docs-worker.toml"),
    Path(".codex/agents/reviewer.toml"),
    Path(".codex/hooks/workflow-evidence.sh"),
    Path(".codex/rules/git.rules"),
    Path(".codex/rules/validation.rules"),
}
BASE_PACKAGE_FILES = {
    Path("AGENTS.md"),
    Path("README.md"),
    Path("LICENSE"),
    Path("pyproject.toml"),
    Path("mkdocs.yml"),
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
} | CODEX_ADAPTER_FILES
BASE_PACKAGE_GITLAB_FILES = (
    BASE_PACKAGE_FILES - {Path(".github/workflows/ci.yml"), Path(".github/workflows/docs.yml")}
) | {Path(".gitlab-ci.yml")}
BASE_MINIMAL_FILES = {
    Path("AGENTS.md"),
    Path("README.md"),
    Path("LICENSE"),
    Path(".gitignore"),
    Path(".github/workflows/ci.yml"),
    Path("scaffold-guard.toml"),
} | CODEX_ADAPTER_FILES
BASE_MINIMAL_GITLAB_FILES = (BASE_MINIMAL_FILES - {Path(".github/workflows/ci.yml")}) | {
    Path(".gitlab-ci.yml")
}
BASE_TYPESCRIPT_FILES = {
    Path("AGENTS.md"),
    Path("README.md"),
    Path("LICENSE"),
    Path("package.json"),
    Path("tsconfig.json"),
    Path("tsconfig.build.json"),
    Path("biome.json"),
    Path("vitest.config.ts"),
    Path(".gitignore"),
    Path(".github/workflows/ci.yml"),
    Path("src/index.ts"),
    Path("tests/index.test.ts"),
    Path("scaffold-guard.toml"),
} | CODEX_ADAPTER_FILES
BASE_MONOREPO_FILES = {
    Path("AGENTS.md"),
    Path("README.md"),
    Path("LICENSE"),
    Path("pyproject.toml"),
    Path("pyrightconfig.json"),
    Path("package.json"),
    Path("biome.json"),
    Path(".gitignore"),
    Path(".github/workflows/ci.yml"),
    Path("packages/python/examples/hello.py"),
    Path("packages/python/src/demo/__init__.py"),
    Path("packages/python/src/demo/core.py"),
    Path("packages/python/src/demo/py.typed"),
    Path("packages/python/tests/unit/test_core.py"),
    Path("packages/python/tests/integration/test_import_package.py"),
    Path("packages/typescript/package.json"),
    Path("packages/typescript/tsconfig.json"),
    Path("packages/typescript/tsconfig.build.json"),
    Path("packages/typescript/vitest.config.ts"),
    Path("packages/typescript/src/index.ts"),
    Path("packages/typescript/tests/index.test.ts"),
    Path("scaffold-guard.toml"),
} | CODEX_ADAPTER_FILES


class GreetingPackage(Protocol):
    """Imported generated package surface used by the smoke test."""

    def greet(self, name: str = "World") -> str:
        """Return a generated greeting."""
        ...


def test_init_codex_generates_valid_package_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The codex adapter creates a base package tree with Codex project files."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["init", "demo", "--profile", "python", "--agent", "codex"])

    assert result.exit_code == SUCCESS, result.output
    project_dir = tmp_path / "demo"
    assert _relative_files(project_dir) == BASE_PACKAGE_FILES
    assert not (project_dir / "CLAUDE.md").exists()
    assert not (project_dir / ".claude").exists()
    assert not (project_dir / ".cursor").exists()
    pyproject = tomllib.loads((project_dir / "pyproject.toml").read_text(encoding="utf-8"))
    config = tomllib.loads((project_dir / "scaffold-guard.toml").read_text(encoding="utf-8"))
    mkdocs_config = (project_dir / "mkdocs.yml").read_text(encoding="utf-8")
    assert pyproject["tool"]["ruff"]["target-version"] == "py313"
    assert pyproject["tool"]["mypy"]["python_version"] == "3.13"
    assert config["project"]["profile"] == "python"
    assert 'site_name: "demo"' in mkdocs_config
    assert "docs_dir: docs" in mkdocs_config
    assert "  - Home: index.md" in mkdocs_config
    assert "Created ScaffoldGuard python project: demo" in result.output
    assert "Codex: AGENTS.md" in result.output
    assert ".codex/agents/*.toml" in result.output
    agents = (project_dir / "AGENTS.md").read_text(encoding="utf-8")
    assert "dataclass(frozen=True, slots=True)" in agents
    assert "TypedDict" in agents
    assert "Use Pydantic only at runtime-validation boundaries" in agents
    assert "Add docstrings to public modules" in agents
    assert "Keep the main thread focused on decisions" in agents
    assert "For non-trivial implementation work, use worker subagents" in agents
    assert "Use read-only subagents for bounded work" in agents
    assert "Use MCP servers when available" in agents

    _assert_no_unresolved_project_placeholders(project_dir)
    _assert_python_files_compile(project_dir)
    with _import_from_project(project_dir):
        package = cast(GreetingPackage, importlib.import_module("demo"))
        assert package.greet("Codex") == "Hello, Codex!"


def test_init_accepts_legacy_package_profile_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The old non-interactive package profile still generates a Python project."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["init", "demo", "--profile", "package", "--agent", "codex"])

    assert result.exit_code == SUCCESS, result.output
    project_dir = tmp_path / "demo"
    config = tomllib.loads((project_dir / "scaffold-guard.toml").read_text(encoding="utf-8"))
    assert config["project"]["profile"] == "python"
    assert (project_dir / "src/demo/core.py").exists()
    assert "Created ScaffoldGuard python project: demo" in result.output


def test_init_can_generate_minimal_gitlab_ci_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The minimal profile can generate GitLab CI instead of GitHub Actions."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["init", "demo", "--ci", "gitlab"])

    assert result.exit_code == SUCCESS, result.output
    project_dir = tmp_path / "demo"
    assert _relative_files(project_dir) >= BASE_MINIMAL_GITLAB_FILES
    assert not (project_dir / ".github").exists()
    config = (project_dir / "scaffold-guard.toml").read_text(encoding="utf-8")
    assert 'ci = "gitlab"' in config
    assert "github_actions = false" in config
    assert "gitlab_ci = true" in config
    assert "CI:\n  - gitlab" in result.output


def test_init_can_generate_python_gitlab_ci_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Python profile can generate GitLab CI instead of GitHub Actions."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["init", "demo", "--profile", "python", "--agent", "codex", "--ci", "gitlab"],
    )

    assert result.exit_code == SUCCESS, result.output
    project_dir = tmp_path / "demo"
    assert _relative_files(project_dir) == BASE_PACKAGE_GITLAB_FILES
    assert not (project_dir / ".github").exists()
    gitlab_ci = (project_dir / ".gitlab-ci.yml").read_text(encoding="utf-8")
    assert "PYTHON_VERSION" in gitlab_ci
    assert "uv run scaffold-guard check" in gitlab_ci
    assert "uv run mkdocs build --strict" in gitlab_ci
    assert "uv run pytest tests --cov=demo" in gitlab_ci


def test_init_python_license_none_omits_pyproject_license_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Python profile omits invalid package license metadata for no-license projects."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["init", "demo", "--profile", "python", "--agent", "codex", "--license", "none"],
    )

    assert result.exit_code == SUCCESS, result.output
    project_dir = tmp_path / "demo"
    pyproject = tomllib.loads((project_dir / "pyproject.toml").read_text(encoding="utf-8"))
    package_json_path = project_dir / "package.json"

    assert "license" not in pyproject["project"]
    assert "No license selected." in (project_dir / "LICENSE").read_text(encoding="utf-8")
    assert not package_json_path.exists()


def test_init_python_profile_python_min_controls_tool_configs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-interactive Python generation propagates python_min to tool config."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "init",
            "demo",
            "--profile",
            "python",
            "--agent",
            "codex",
            "--python-min",
            "3.14",
            "--coverage",
            str(FULL_COVERAGE),
        ],
    )

    assert result.exit_code == SUCCESS, result.output
    project_dir = tmp_path / "demo"
    pyproject = tomllib.loads((project_dir / "pyproject.toml").read_text(encoding="utf-8"))
    config = tomllib.loads((project_dir / "scaffold-guard.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["requires-python"] == ">=3.14"
    assert pyproject["tool"]["ruff"]["target-version"] == "py314"
    assert pyproject["tool"]["mypy"]["python_version"] == "3.14"
    assert pyproject["tool"]["coverage"]["report"]["fail_under"] == FULL_COVERAGE
    assert config["project"]["python_min"] == "3.14"
    assert config["project"]["coverage_fail_under"] == FULL_COVERAGE


def test_init_can_generate_typescript_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The TypeScript profile creates a strict npm-based package scaffold."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["init", "demo", "--profile", "typescript", "--agent", "codex"],
    )

    assert result.exit_code == SUCCESS, result.output
    project_dir = tmp_path / "demo"
    assert _relative_files(project_dir) == BASE_TYPESCRIPT_FILES
    assert not (project_dir / "pyproject.toml").exists()
    assert not (project_dir / ".claude").exists()
    assert not (project_dir / ".cursor").exists()
    package_json = json.loads((project_dir / "package.json").read_text(encoding="utf-8"))
    config = tomllib.loads((project_dir / "scaffold-guard.toml").read_text(encoding="utf-8"))
    _assert_json_has_no_blank_lines(project_dir / "package.json")
    assert package_json["scripts"]["typecheck"] == "tsc --noEmit"
    assert package_json["devDependencies"]["@biomejs/biome"].startswith("^2.")
    assert config["project"]["profile"] == "typescript"
    assert config["features"]["typescript"] is True
    assert config["tools"]["biome"] is True
    assert "npm install" in result.output
    assert "uv sync --all-groups" not in result.output
    _assert_no_unresolved_project_placeholders(project_dir)


def test_init_typescript_profile_biome_package_json_is_formatted_without_vitest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Biome-enabled TypeScript scaffolds keep package.json formatter-clean without Vitest."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "init",
            "demo",
            "--profile",
            "typescript",
            "--agent",
            "codex",
            "--typescript-lint",
            "biome",
            "--typescript-test",
            "off",
        ],
    )

    assert result.exit_code == SUCCESS, result.output
    project_dir = tmp_path / "demo"
    package_json = json.loads((project_dir / "package.json").read_text(encoding="utf-8"))

    _assert_json_has_no_blank_lines(project_dir / "package.json")
    assert set(package_json["scripts"]) == {"format", "format:check", "lint", "typecheck", "build"}
    assert set(package_json["devDependencies"]) == {"@biomejs/biome", "typescript"}


def test_init_typescript_profile_can_disable_optional_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TypeScript scaffolds can opt out of Biome, Vitest, and strict mode."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "init",
            "demo",
            "--profile",
            "typescript",
            "--agent",
            "codex",
            "--typescript-mode",
            "standard",
            "--typescript-lint",
            "off",
            "--typescript-test",
            "off",
        ],
    )

    assert result.exit_code == SUCCESS, result.output
    project_dir = tmp_path / "demo"
    files = _relative_files(project_dir)
    package_json = json.loads((project_dir / "package.json").read_text(encoding="utf-8"))
    tsconfig = json.loads((project_dir / "tsconfig.json").read_text(encoding="utf-8"))
    ci_workflow = (project_dir / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    readme = (project_dir / "README.md").read_text(encoding="utf-8")
    agents = (project_dir / "AGENTS.md").read_text(encoding="utf-8")
    config = tomllib.loads((project_dir / "scaffold-guard.toml").read_text(encoding="utf-8"))

    _assert_json_has_no_blank_lines(project_dir / "package.json")
    assert Path("biome.json") not in files
    assert Path("vitest.config.ts") not in files
    assert Path("tests/index.test.ts") not in files
    assert set(package_json["scripts"]) == {"typecheck", "build"}
    assert set(package_json["devDependencies"]) == {"typescript"}
    assert tsconfig["compilerOptions"]["strict"] is False
    assert tsconfig["include"] == ["src/**/*.ts"]
    assert config["tools"]["typescript_strict"] is False
    assert config["tools"]["biome"] is False
    assert config["tools"]["vitest"] is False
    assert "npm run format:check" not in ci_workflow
    assert "npm test" not in ci_workflow
    assert "npm run coverage" not in ci_workflow
    assert "npm run typecheck" in ci_workflow
    assert "npm run build" in ci_workflow
    assert "npm run format:check" not in readme
    assert "npm test" not in agents
    assert "Biome: disabled" in result.output
    assert "Vitest: disabled" in result.output


def test_check_passes_in_fresh_typescript_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fresh TypeScript project passes ScaffoldGuard policy checks."""
    monkeypatch.chdir(tmp_path)
    init_result = CliRunner().invoke(
        app,
        ["init", "demo", "--profile", "typescript", "--agent", "all"],
    )

    assert init_result.exit_code == SUCCESS, init_result.output

    check_result = CliRunner().invoke(app, ["check", "--path", "demo"])

    assert check_result.exit_code == SUCCESS, check_result.output
    files = _relative_files(tmp_path / "demo")
    assert Path(".claude/rules/typescript.md") in files
    assert Path(".cursor/rules/typescript.mdc") in files
    assert Path(".claude/rules/python.md") not in files
    assert Path(".cursor/rules/python.mdc") not in files


def test_init_can_generate_python_typescript_monorepo_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The monorepo profile creates Python and TypeScript package workspaces."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["init", "demo", "--profile", "monorepo", "--agent", "codex"],
    )

    assert result.exit_code == SUCCESS, result.output
    project_dir = tmp_path / "demo"
    assert _relative_files(project_dir) == BASE_MONOREPO_FILES
    pyproject = (project_dir / "pyproject.toml").read_text(encoding="utf-8")
    package_json = json.loads((project_dir / "package.json").read_text(encoding="utf-8"))
    biome_json = json.loads((project_dir / "biome.json").read_text(encoding="utf-8"))
    config = tomllib.loads((project_dir / "scaffold-guard.toml").read_text(encoding="utf-8"))
    assert 'packages = ["packages/python/src/demo"]' in pyproject
    _assert_json_has_no_blank_lines(project_dir / "package.json")
    _assert_json_has_no_blank_lines(project_dir / "packages/typescript/package.json")
    assert package_json["workspaces"] == ["packages/typescript"]
    assert package_json["scripts"]["ts:typecheck"].startswith("tsc -p packages/typescript")
    assert biome_json["files"]["includes"] == [
        "packages/typescript/**",
        "!!packages/typescript/dist",
        "!!packages/typescript/coverage",
    ]
    assert config["project"]["profile"] == "monorepo"
    assert config["features"]["python"] is True
    assert config["features"]["typescript"] is True
    assert "uv sync --all-groups" in result.output
    assert "npm install" in result.output
    _assert_no_unresolved_project_placeholders(project_dir)
    _assert_python_files_compile(project_dir)


def test_init_monorepo_license_none_omits_python_pyproject_license_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The monorepo profile keeps Python metadata buildable when no license is selected."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["init", "demo", "--profile", "monorepo", "--agent", "codex", "--license", "none"],
    )

    assert result.exit_code == SUCCESS, result.output
    project_dir = tmp_path / "demo"
    pyproject = tomllib.loads((project_dir / "pyproject.toml").read_text(encoding="utf-8"))
    root_package_json = json.loads((project_dir / "package.json").read_text(encoding="utf-8"))
    workspace_package_json = json.loads(
        (project_dir / "packages/typescript/package.json").read_text(encoding="utf-8")
    )

    assert "license" not in pyproject["project"]
    assert "license" not in root_package_json
    assert "license" not in workspace_package_json
    assert "No license selected." in (project_dir / "LICENSE").read_text(encoding="utf-8")


def test_init_monorepo_python_min_controls_python_tool_configs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-interactive monorepo generation propagates python_min to Python tool config."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "init",
            "demo",
            "--profile",
            "monorepo",
            "--agent",
            "codex",
            "--python-min",
            "3.14",
            "--coverage",
            str(FULL_COVERAGE),
        ],
    )

    assert result.exit_code == SUCCESS, result.output
    project_dir = tmp_path / "demo"
    pyproject = tomllib.loads((project_dir / "pyproject.toml").read_text(encoding="utf-8"))
    config = tomllib.loads((project_dir / "scaffold-guard.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["requires-python"] == ">=3.14"
    assert pyproject["tool"]["ruff"]["target-version"] == "py314"
    assert pyproject["tool"]["mypy"]["python_version"] == "3.14"
    assert pyproject["tool"]["coverage"]["report"]["fail_under"] == FULL_COVERAGE
    assert config["project"]["python_min"] == "3.14"
    assert config["project"]["coverage_fail_under"] == FULL_COVERAGE


def test_init_monorepo_profile_can_disable_typescript_optional_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Monorepo scaffolds honor TypeScript tool selections."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "init",
            "demo",
            "--profile",
            "monorepo",
            "--agent",
            "codex",
            "--typescript-lint",
            "off",
            "--typescript-test",
            "off",
        ],
    )

    assert result.exit_code == SUCCESS, result.output
    project_dir = tmp_path / "demo"
    files = _relative_files(project_dir)
    package_json = json.loads((project_dir / "package.json").read_text(encoding="utf-8"))
    ci_workflow = (project_dir / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    readme = (project_dir / "README.md").read_text(encoding="utf-8")
    agents = (project_dir / "AGENTS.md").read_text(encoding="utf-8")
    config = tomllib.loads((project_dir / "scaffold-guard.toml").read_text(encoding="utf-8"))

    _assert_json_has_no_blank_lines(project_dir / "package.json")
    _assert_json_has_no_blank_lines(project_dir / "packages/typescript/package.json")
    assert Path("biome.json") not in files
    assert Path("packages/typescript/vitest.config.ts") not in files
    assert Path("packages/typescript/tests/index.test.ts") not in files
    assert set(package_json["scripts"]) == {"ts:typecheck", "ts:build"}
    assert set(package_json["devDependencies"]) == {"typescript"}
    assert config["tools"]["biome"] is False
    assert config["tools"]["vitest"] is False
    assert "npm run ts:format:check" not in ci_workflow
    assert "npm run ts:test" not in ci_workflow
    assert "npm run ts:coverage" not in ci_workflow
    assert "npm run ts:typecheck" in ci_workflow
    assert "npm run ts:build" in ci_workflow
    assert "npm run ts:format:check" not in readme
    assert "npm run ts:test" not in agents


def test_init_python_can_disable_quality_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Python scaffolds can opt out of Ruff, mypy, and Pyright."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["init", "demo", "--guided"],
        input="\ncodex\npython\nMIT\n3.13\noff\noff\n95\ngithub\n",
    )

    assert result.exit_code == SUCCESS, result.output
    project_dir = tmp_path / "demo"
    assert Path("pyrightconfig.json") not in _relative_files(project_dir)
    pyproject = (project_dir / "pyproject.toml").read_text(encoding="utf-8")
    ci_workflow = (project_dir / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    config = (project_dir / "scaffold-guard.toml").read_text(encoding="utf-8")
    agents = (project_dir / "AGENTS.md").read_text(encoding="utf-8")

    assert '"ruff>=' not in pyproject
    assert '"mypy>=' not in pyproject
    assert '"pyright>=' not in pyproject
    assert "[tool.ruff]" not in pyproject
    assert "[tool.mypy]" not in pyproject
    assert tomllib.loads(pyproject)["dependency-groups"]
    assert tomllib.loads(config)["tools"] == {
        "ruff": False,
        "ruff_mode": "off",
        "mypy": False,
        "pyright": False,
        "python_typecheck": "off",
        "python_typechecker": "mypy+pyright",
    }
    assert tomllib.loads(config)["project"]["profile"] == "python"
    assert "ruff" not in ci_workflow
    assert "mypy" not in ci_workflow
    assert "pyright" not in ci_workflow.lower()
    assert "ruff = false" in config
    assert "mypy = false" in config
    assert "pyright = false" in config
    assert "forbid_noqa = false" in config
    assert "forbid_type_ignore = false" in config
    assert "forbid_pyright_ignore = false" in config
    assert "Ruff: disabled" in result.output
    assert "Type checking: disabled" in result.output
    assert "mypy: disabled" in result.output
    assert "Pyright: disabled" in result.output
    assert "ScaffoldGuard guided setup" in result.output
    assert "uv run ruff" not in agents
    assert "uv run mypy" not in agents
    assert "uv run pyright" not in agents


def test_init_python_can_use_standard_quality_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Python scaffolds can use non-strict Ruff and type-checking modes."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "init",
            "demo",
            "--profile",
            "python",
            "--agent",
            "codex",
            "--ruff",
            "standard",
            "--python-typecheck",
            "standard",
            "--python-typechecker",
            "mypy+pyright",
        ],
    )

    assert result.exit_code == SUCCESS, result.output
    project_dir = tmp_path / "demo"
    pyproject = (project_dir / "pyproject.toml").read_text(encoding="utf-8")
    pyright = json.loads((project_dir / "pyrightconfig.json").read_text(encoding="utf-8"))
    config = tomllib.loads((project_dir / "scaffold-guard.toml").read_text(encoding="utf-8"))

    assert '"ANN"' not in pyproject
    assert '"PL"' not in pyproject
    assert "strict = true" not in pyproject
    assert "check_untyped_defs = true" in pyproject
    assert config["tools"]["ruff_mode"] == "standard"
    assert config["tools"]["python_typecheck"] == "standard"
    assert config["tools"]["python_typechecker"] == "mypy+pyright"
    assert config["tools"]["mypy"] is True
    assert config["tools"]["pyright"] is True
    assert pyright["typeCheckingMode"] == "standard"
    assert "Ruff: standard" in result.output
    assert "Type checking: standard" in result.output
    assert "Typechecker: mypy+pyright" in result.output


@pytest.mark.parametrize(
    ("checker", "expected_mypy", "expected_pyright"),
    [
        ("mypy", True, False),
        ("pyright", False, True),
    ],
)
def test_init_python_typechecker_selection_controls_generated_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    checker: str,
    expected_mypy: bool,
    expected_pyright: bool,
) -> None:
    """Python typechecker selection controls dependencies, files, CI, and agent commands."""
    monkeypatch.chdir(tmp_path)
    project_name = f"demo_{checker}"

    result = CliRunner().invoke(
        app,
        [
            "init",
            project_name,
            "--profile",
            "python",
            "--agent",
            "codex",
            "--python-typechecker",
            checker,
        ],
    )

    assert result.exit_code == SUCCESS, result.output
    project_dir = tmp_path / project_name
    pyproject = (project_dir / "pyproject.toml").read_text(encoding="utf-8")
    ci_workflow = (project_dir / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    agents = (project_dir / "AGENTS.md").read_text(encoding="utf-8")
    config = tomllib.loads((project_dir / "scaffold-guard.toml").read_text(encoding="utf-8"))

    assert config["tools"]["python_typecheck"] == "strict"
    assert config["tools"]["python_typechecker"] == checker
    assert config["tools"]["mypy"] is expected_mypy
    assert config["tools"]["pyright"] is expected_pyright
    assert ('"mypy>=' in pyproject) is expected_mypy
    assert ("uv run mypy" in ci_workflow) is expected_mypy
    assert ("uv run mypy" in agents) is expected_mypy
    assert ('"pyright>=' in pyproject) is expected_pyright
    assert ("uv run pyright" in ci_workflow) is expected_pyright
    assert ("uv run pyright" in agents) is expected_pyright
    assert (project_dir / "pyrightconfig.json").exists() is expected_pyright
    if expected_pyright:
        pyright = json.loads((project_dir / "pyrightconfig.json").read_text(encoding="utf-8"))
        assert pyright["typeCheckingMode"] == "strict"
    assert f"Typechecker: {checker}" in result.output
    assert f"mypy: {'enabled' if expected_mypy else 'disabled'}" in result.output
    assert f"Pyright: {'enabled' if expected_pyright else 'disabled'}" in result.output


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
    assert _relative_files(tmp_path / "demo") >= BASE_MINIMAL_FILES
    assert not (tmp_path / "demo/src").exists()
    config = (tmp_path / "demo/scaffold-guard.toml").read_text(encoding="utf-8")
    assert 'profile = "minimal"' in config


def test_check_text_output_reports_failure_locations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Text mode lists findings with path and line number."""
    monkeypatch.chdir(tmp_path)
    init_result = CliRunner().invoke(
        app,
        ["init", "demo", "--profile", "python", "--agent", "codex"],
    )
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
    assert BASE_MINIMAL_FILES.issubset(files)
    assert Path("pyproject.toml") not in files
    assert Path("src/demo/core.py") not in files
    assert Path("CLAUDE.md") in files
    assert Path(".claude/rules/testing.md") in files
    assert Path(".cursor/rules/testing.mdc") in files
    assert Path(".claude/rules/python.md") not in files
    assert Path(".cursor/rules/python.mdc") not in files
    assert "@AGENTS.md" in (project_dir / "CLAUDE.md").read_text(encoding="utf-8")
    agents = (project_dir / "AGENTS.md").read_text(encoding="utf-8")
    cursor_testing = (project_dir / ".cursor/rules/testing.mdc").read_text(encoding="utf-8")
    assert "alwaysApply: false" in cursor_testing
    assert "For non-trivial implementation work, use worker subagents" in agents
    assert "Use read-only subagents for bounded work" in agents
    assert "Use dataclasses for internal structured state" in agents
    assert "TypedDict" in agents
    assert "Claude Code: CLAUDE.md + .claude/rules/" in result.output
    assert "Cursor: .cursor/rules/*.mdc + AGENTS.md" in result.output
    assert ".codex/agents/*.toml" in result.output


def test_init_without_name_runs_guided_setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Omitting NAME starts guided setup and uses prompted values."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["init"],
        input=(
            "guided-demo\nclaude\npython\nApache-2.0\n3.14\nstrict\nstrict\n"
            "mypy+pyright\n90\ngithub\n"
        ),
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
    assert 'profile = "python"' in config
    assert 'python_min = "3.14"' in config
    assert "coverage_fail_under = 90" in config
    assert "ScaffoldGuard guided setup" in result.output
    assert "minimal: guardrails only; no Python or TypeScript source scaffold" in result.output
    assert "Project profile (minimal/python/typescript/monorepo)" in result.output
    assert "python: Python package scaffold with src/, tests/, docs/, and uv" in result.output
    assert "package: Python package scaffold" not in result.output
    assert "typescript: TypeScript package scaffold with npm and configurable tooling" in (
        result.output
    )
    assert "monorepo: Python + TypeScript workspaces under packages/" in result.output
    assert "Created ScaffoldGuard python project: guided-demo" in result.output


def test_init_guided_monorepo_prompts_for_language_tool_setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guided monorepo setup asks for Python and TypeScript tool choices."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["init"],
        input=(
            "guided-monorepo\ncodex\nmonorepo\nMIT\n3.13\nstrict\nstrict\n"
            "mypy+pyright\nstrict\nbiome\nvitest\n95\ngithub\n"
        ),
    )

    assert result.exit_code == SUCCESS, result.output
    assert (tmp_path / "guided-monorepo/packages/typescript/src/index.ts").exists()
    assert "Ruff strictness (strict/standard/off)" in result.output
    assert "Python type-check strictness (strict/standard/off)" in result.output
    assert "Python typechecker (mypy+pyright/mypy/pyright)" in result.output
    assert "TypeScript mode (strict/standard)" in result.output
    assert "TypeScript formatter/linter (biome/off)" in result.output
    assert "TypeScript test runner (vitest/off)" in result.output


def test_init_guided_recovers_from_invalid_prompt_answers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guided setup reports invalid choices and asks again."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["init"],
        input=(
            "demo\nbad-agent\ncodex\npackage\npython\nMIT\n3.13\n"
            "maybe\nstrict\nbad-type\nstandard\nbad-checker\nmypy+pyright\n"
            "not-a-number\n101\n95\ngithub\n"
        ),
    )

    assert result.exit_code == SUCCESS, result.output
    assert (tmp_path / "demo/AGENTS.md").exists()
    assert not (tmp_path / "demo/CLAUDE.md").exists()
    assert "Choose one of: codex, claude, cursor, all" in result.output
    assert "Choose one of: minimal, python, typescript, monorepo" in result.output
    assert "Choose one of: strict, standard, off" in result.output
    assert "Choose one of: mypy+pyright, mypy, pyright" in result.output
    assert "Test coverage floor must be an integer." in result.output
    assert "Test coverage floor must be between 1 and 100." in result.output


def test_init_help_explains_profile_choices() -> None:
    """The init help text makes profile names understandable."""
    result = CliRunner().invoke(app, ["init", "--help"])

    assert result.exit_code == SUCCESS, result.output
    assert "minimal" in result.output
    assert "guardrails only" in result.output
    assert "source scaffold" in result.output
    assert "python" in result.output
    assert "Python package" in result.output
    assert "package Python package scaffold" not in result.output
    assert "typescript" in result.output
    assert "TypeScript package" in result.output
    assert "monorepo" in result.output
    assert "workspaces" in result.output


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
    assert not (project_dir / "src").exists()
    assert 'profile = "minimal"' in (project_dir / "scaffold-guard.toml").read_text(
        encoding="utf-8"
    )
    assert not (project_dir / "already-created").exists()
    assert "ScaffoldGuard guided setup" not in result.output
    assert "Created ScaffoldGuard minimal project: already-created" in result.output
    assert "  cd already-created" not in result.output


def test_init_dot_without_explicit_options_runs_guided_setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bare `init .` remains a guided compatibility path for current-directory init."""
    project_dir = tmp_path / "guided-dot"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)

    result = CliRunner().invoke(app, ["init", "."], input="\ncodex\n\n\n\n")

    assert result.exit_code == SUCCESS, result.output
    assert (project_dir / "AGENTS.md").exists()
    assert not (project_dir / "src").exists()
    assert not (project_dir / ".cursor").exists()
    assert "ScaffoldGuard guided setup" in result.output
    assert "Created ScaffoldGuard minimal project: guided-dot" in result.output
    assert "  cd guided-dot" not in result.output


def test_init_guided_accepts_empty_name_for_current_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guided setup treats an empty project name as the current directory."""
    project_dir = tmp_path / "guided-current"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)

    result = CliRunner().invoke(app, ["init"], input="\ncodex\n\n\n\n")

    assert result.exit_code == SUCCESS, result.output
    assert (project_dir / "AGENTS.md").exists()
    assert not (project_dir / "src").exists()
    assert "Project name (Enter for current directory)" in result.output
    assert "Created ScaffoldGuard minimal project: guided-current" in result.output
    assert "  cd guided-current" not in result.output


def test_init_guided_accepts_dot_for_current_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guided setup keeps dot accepted as a current-directory alias."""
    project_dir = tmp_path / "guided-dot-alias"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)

    result = CliRunner().invoke(app, ["init"], input=".\ncodex\n\n\n\n")

    assert result.exit_code == SUCCESS, result.output
    assert (project_dir / "AGENTS.md").exists()
    assert not (project_dir / "src").exists()
    assert "Created ScaffoldGuard minimal project: guided-dot-alias" in result.output


def test_init_dry_run_creates_no_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dry-run reports planned files but leaves the target absent."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["init", "demo", "--agent", "codex", "--dry-run"])

    assert result.exit_code == SUCCESS, result.output
    assert "Planned ScaffoldGuard minimal project: demo" in result.output
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


def _assert_json_has_no_blank_lines(path: Path) -> None:
    """Fail when generated JSON contains blank lines rejected by Biome formatting."""
    text = path.read_text(encoding="utf-8")
    assert "\n\n" not in text


def _assert_python_files_compile(project_dir: Path) -> None:
    """Compile generated Python files without importing test modules."""
    for path in project_dir.rglob("*.py"):
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
