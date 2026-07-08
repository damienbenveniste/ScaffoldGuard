# V1 Implementation Plan: `scaffold-guard`

**Purpose:** Implementation-ready plan for a coding agent to build V1 of a PyPI-installable starter CLI that creates **scaffold-guard repositories** with first-class **Codex**, **Claude Code**, and **Cursor** support.

**Working PyPI package name:** `scaffold-guard`
**Working CLI command:** `scaffold-guard`
**V1 user-facing promise:** “Generate a strict starter repository that is ready for coding agents, with clear instructions, strict CI, and local policy checks that stop common agent mistakes.”

---

## 0. Executive Summary

Build a Python CLI package published to PyPI. Users install it normally. The CLI scaffolds a new guarded repository with:

- strict Python packaging defaults;
- `uv`-based local workflow;
- Ruff, mypy, Pyright, pytest, coverage, MkDocs;
- GitHub Actions CI;
- `AGENTS.md` as the shared cross-agent instruction surface;
- Codex-first support through `AGENTS.md`;
- Claude Code support through `CLAUDE.md` importing `AGENTS.md`, plus optional `.claude/rules/`;
- Cursor support through `.cursor/rules/*.mdc`, plus `AGENTS.md`;
- local policy checks for common coding-agent failure modes;
- a diff-aware “what checks are required?” command.

V1 should be small enough to ship, but serious enough to demonstrate expert-level AI engineering discipline.

---

## 1. Product Frame for V1

Do not implement a SaaS, dashboard, telemetry system, or complex rules engine in V1.

Implement a **developer CLI** that answers:

> “How do I start a Python repo that coding agents can work in safely?”

### 1.1 Target user

A Python developer who uses one or more coding agents:

- OpenAI Codex;
- Claude Code;
- Cursor;
- possibly GitHub Actions and `uv`.

### 1.2 Primary V1 use cases

A user should be able to run:

```bash
uv tool install scaffold-guard
scaffold-guard init my_project --agent codex
scaffold-guard init my_project --agent claude
scaffold-guard init my_project --agent cursor
scaffold-guard init my_project --agent all
```

Then:

```bash
cd my_project
uv sync --all-groups
uv run scaffold-guard check
uv run scaffold-guard inspect-diff
uv run scaffold-guard validate
```

The generated repo should already contain enough context for a coding agent to know:

- where source, tests, docs, and examples live;
- what commands to run;
- what patterns are forbidden;
- what must be updated when public behavior changes;
- what the final response should include after implementation work.

---

## 2. Important External Adapter Facts

These facts shape adapter generation. Keep them in the README and in code comments near adapter implementations.

### 2.1 Codex

V1 should treat **Codex as first-class through `AGENTS.md`**.

Codex currently supports `AGENTS.md` as a custom instruction mechanism. It reads `AGENTS.md` files before work, builds an instruction chain across global and project scopes, and supports nested project guidance. V1 should generate a high-quality root `AGENTS.md` and optionally support nested `AGENTS.md` later.

Codex also has docs for rules and hooks, but V1 should not implement Codex hooks by default. Add a TODO / V1.1 section for `.codex` hooks because hooks are an enforcement layer and will require careful testing.

### 2.2 Claude Code

Claude Code reads `CLAUDE.md`, not `AGENTS.md`. Therefore V1 must generate:

```markdown
@AGENTS.md

## Claude Code

- Use this file as a Claude-specific wrapper around the shared project rules.
```

When selected, Claude support may also generate modular `.claude/rules/*.md` files.

V1 rule:

- `AGENTS.md` is the source of shared behavior.
- `CLAUDE.md` imports `AGENTS.md`.
- `.claude/rules/` adds Claude-specific path-scoped guidance only when useful.

### 2.3 Cursor

Cursor supports structured project rules in `.cursor/rules/*.mdc`, and also supports `AGENTS.md` as a simpler markdown instruction file.

V1 Cursor support should generate:

```text
AGENTS.md
.cursor/rules/python.mdc
.cursor/rules/testing.mdc
.cursor/rules/docs.mdc
.cursor/rules/security.mdc
.cursor/rules/git-hygiene.mdc
```

Cursor `.mdc` files require frontmatter. Use `alwaysApply`, `description`, and optionally `globs`.

### 2.4 V1 adapter strategy

Always generate `AGENTS.md`.

Then generate adapter-specific files according to `--agent`:

| `--agent` value | Files |
|---|---|
| `codex` | `AGENTS.md` |
| `claude` | `AGENTS.md`, `CLAUDE.md`, `.claude/rules/*.md` |
| `cursor` | `AGENTS.md`, `.cursor/rules/*.mdc` |
| `all` | all of the above |

---

## 3. V1 Scope

### 3.1 Must have

Implement these commands:

```bash
scaffold-guard init NAME [options]
scaffold-guard check [options]
scaffold-guard inspect-diff [options]
scaffold-guard validate [options]
scaffold-guard compile-rules [options]
scaffold-guard doctor [options]
scaffold-guard version
```

### 3.2 Must generate

For the default `minimal` profile, generate guardrails only:

```text
my_project/
  AGENTS.md
  README.md
  LICENSE
  .gitignore
  scaffold-guard.toml
  .github/
    workflows/
      ci.yml
```

For the explicit `python` profile, also generate:

```text
my_project/
  AGENTS.md
  README.md
  LICENSE
  pyproject.toml
  pyrightconfig.json
  .gitignore
  .github/
    workflows/
      ci.yml
      docs.yml
  docs/
    index.md
  examples/
    hello.py
  src/
    my_project/
      __init__.py
      py.typed
      core.py
  tests/
    unit/
      test_core.py
    integration/
      test_import_package.py
  scaffold-guard.toml
```

Depending on `--agent`, also generate:

```text
CLAUDE.md
.claude/
  rules/
    python.md
    testing.md
    docs.md
    security.md
    git-hygiene.md

.cursor/
  rules/
    python.mdc
    testing.mdc
    docs.mdc
    security.mdc
    git-hygiene.mdc
```

### 3.3 Should have

- `--dry-run` for `init` and `compile-rules`.
- `--force` for overwriting existing generated files.
- `--no-ci`, `--no-docs`, and `--license`.
- `--json` output for `check`, `inspect-diff`, and `doctor`.
- idempotent `compile-rules`.

### 3.4 Non-goals for V1

Do not implement:

- Homebrew formula automation;
- real CD/deployment workflows;
- TestPyPI/PyPI publish automation for generated projects;
- telemetry;
- SaaS dashboard;
- external AI calls;
- network access from tests;
- full plugin ecosystem;
- complex YAML DSL;
- automatic mutation of an existing mature repo.

V1 may include documentation that says Homebrew is planned after PyPI is stable.

---

## 4. Repository Layout for the CLI Package

Create the implementation repository like this:

```text
scaffold-guard/
  AGENTS.md
  README.md
  LICENSE
  pyproject.toml
  pyrightconfig.json
  mkdocs.yml
  docs/
    index.md
    quickstart.md
    adapters.md
    generated-project.md
    checks.md
    releasing.md
  src/
    scaffold_guard/
      __init__.py
      __main__.py
      cli.py
      constants.py
      exceptions.py
      fs.py
      models.py
      renderer.py
      scaffold.py
      diffing.py
      validators.py
      adapters/
        __init__.py
        base.py
        codex.py
        claude.py
        cursor.py
      checks/
        __init__.py
        base.py
        unsafe_patterns.py
        diff_requirements.py
        project_health.py
        generated_files.py
      templates/
        package/
          AGENTS.md.j2
          README.md.j2
          LICENSE.j2
          pyproject.toml.j2
          pyrightconfig.json.j2
          gitignore.j2
          scaffold-guard.toml.j2
          docs/index.md.j2
          examples/hello.py.j2
          src/package/__init__.py.j2
          src/package/core.py.j2
          src/package/py.typed.j2
          tests/unit/test_core.py.j2
          tests/integration/test_import_package.py.j2
          github/workflows/ci.yml.j2
          github/workflows/docs.yml.j2
        agents/
          claude/CLAUDE.md.j2
          claude/rules/python.md.j2
          claude/rules/testing.md.j2
          claude/rules/docs.md.j2
          claude/rules/security.md.j2
          claude/rules/git-hygiene.md.j2
          cursor/rules/python.mdc.j2
          cursor/rules/testing.mdc.j2
          cursor/rules/docs.mdc.j2
          cursor/rules/security.mdc.j2
          cursor/rules/git-hygiene.mdc.j2
  tests/
    unit/
      test_cli_init.py
      test_renderer.py
      test_scaffold.py
      test_adapters.py
      test_unsafe_patterns.py
      test_diff_requirements.py
      test_project_health.py
    integration/
      test_generated_package_profile.py
      test_compile_rules_idempotent.py
      test_validate_smoke.py
```

Use `importlib.resources.files()` to load packaged templates.

---

## 5. Package Metadata and Dependencies

### 5.1 CLI package Python target

The CLI itself should support Python `>=3.11`.

Generated projects should target Python `>=3.13`.

Rationale:

- supporting Python 3.11 makes the CLI easier to install;
- generated projects can be stricter and more forward-looking.

### 5.2 CLI package dependencies

Use minimal but productive dependencies:

```toml
[project]
name = "scaffold-guard"
version = "0.1.0"
description = "Generate guarded starter repositories for Codex, Claude Code, and Cursor."
requires-python = ">=3.11"
dependencies = [
  "jinja2>=3.1.0",
  "packaging>=24.0",
  "rich>=13.7.0",
  "typer>=0.12.0",
]
```

Avoid `pydantic` for the CLI internals in V1 unless absolutely needed. Keeping the generator lightweight improves install speed.

### 5.3 CLI entry point

```toml
[project.scripts]
scaffold-guard = "scaffold_guard.cli:app"
```

### 5.4 Package data

Make sure template files are included in the built wheel.

Use either Hatchling package-data config or setuptools package-data. Prefer Hatchling.

Example:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/scaffold_guard"]

[tool.hatch.build.targets.wheel.force-include]
"src/scaffold_guard/templates" = "scaffold_guard/templates"
```

Confirm this with a wheel build test.

---

## 6. CLI Command Specification

## 6.1 `scaffold-guard init`

### Command

```bash
scaffold-guard init NAME \
  --agent codex|claude|cursor|all \
  --profile minimal|python \
  --license MIT|Apache-2.0|none \
  --python-min 3.13 \
  --coverage 95 \
  --ci github \
  --dry-run \
  --force
```

### Defaults

```text
--agent all
--profile minimal
--license MIT
--python-min 3.13
--coverage 95
--ci github
--dry-run false
--force false
```

### Behavior

1. Validate `NAME`.
2. Convert `NAME` to:
   - project directory name;
   - Python package import name.
3. Refuse unsafe names:
   - empty;
   - path traversal;
   - absolute paths unless explicitly allowed by a future flag;
   - names that produce invalid package identifiers.
4. If target directory exists:
   - fail unless `--force`;
   - if `--force`, only overwrite known generated files.
5. Render templates into target.
6. Write a summary:
   - created files;
   - selected agent adapters;
   - next commands.
7. If `--dry-run`, do not write anything.

### Example output

```text
Created scaffold-guard project: my-project

Agent adapters:
  ✓ Codex: AGENTS.md
  ✓ Claude Code: CLAUDE.md + .claude/rules/
  ✓ Cursor: .cursor/rules/*.mdc + AGENTS.md

Next:
  cd my-project
  uv sync --all-groups
  uv run scaffold-guard check
  uv run scaffold-guard validate
```

### Acceptance tests

- `init demo --agent codex` creates `AGENTS.md` and not `CLAUDE.md` or `.cursor/`.
- `init demo --agent claude` creates `AGENTS.md`, `CLAUDE.md`, and `.claude/rules/`.
- `init demo --agent cursor` creates `AGENTS.md` and `.cursor/rules/*.mdc`.
- `init demo --agent all` creates all adapter files.
- `init demo --dry-run` creates no files.
- `init ../escape` fails.
- `init "bad-name!"` either fails or normalizes with clear output. Prefer fail in V1.
- existing directory requires `--force`.

---

## 6.2 `scaffold-guard check`

### Command

```bash
scaffold-guard check [--path .] [--json]
```

### Purpose

Run fast local policy checks that do not require executing all project tests.

### V1 checks

Implement these checkers:

1. `unsafe-patterns`
2. `project-health`
3. `generated-files`
4. `config-consistency`

### `unsafe-patterns` must detect

Fail on these patterns in project source, tests, docs examples, and generated agent instructions unless allowed by an inline allow comment:

- `# type: ignore`
- `# pyright: ignore`
- `# noqa:`
- `dict[str, Any]`
- `Any` imports from `typing` in project code
- suspicious secret literals:
  - `OPENAI_API_KEY=sk-`
  - `ANTHROPIC_API_KEY=`
  - `AWS_SECRET_ACCESS_KEY=`
  - generic `password = "..."`
- `subprocess.run(..., shell=True)` in source and tests
- direct writes outside project root in generated scripts
- committed `.env`
- committed `.venv`
- committed `.replaylab` or other runtime artifact directories if included later

Do not make the first implementation over-smart. Regex-based scanning is acceptable in V1.

Add a documented escape hatch:

```python
# scaffold-guard: allow[type-ignore] reason="third-party package has broken stubs"
```

But V1 may implement the parser after shipping. For the first pass, detect all instances and document that allow comments are V1.1.

### `project-health` must verify

- `pyproject.toml` exists.
- `pyrightconfig.json` exists.
- `AGENTS.md` exists.
- `src/` exists.
- `tests/` exists.
- `docs/` exists unless docs are disabled in `scaffold-guard.toml`.
- `.github/workflows/ci.yml` exists unless CI is disabled in `scaffold-guard.toml`.
- if `CLAUDE.md` exists, it imports or references `AGENTS.md`.
- if `.cursor/rules` exists, rules use `.mdc` extension and have frontmatter.

### `generated-files` must verify

- no generated adapter file contains unresolved Jinja placeholders like `{{`.
- `.cursor/rules/*.mdc` frontmatter parses enough to see `alwaysApply`, `description`, or `globs`.
- generated README commands mention `uv`.
- generated CI uses `uv sync`, Ruff, mypy, Pyright, pytest, and MkDocs unless disabled.

### `config-consistency` must verify

- `scaffold-guard.toml` selected agents match the files present.
- `coverage_fail_under` in `scaffold-guard.toml` matches `pyproject.toml` coverage config if present.
- `python_min` in `scaffold-guard.toml` matches generated `pyproject.toml`.
- if dependencies in `pyproject.toml` changed and `uv.lock` exists, warn if `uv.lock` is older than `pyproject.toml`.

### Exit codes

```text
0 = all checks pass
1 = policy failures
2 = invalid configuration or tool error
```

### JSON output shape

```json
{
  "ok": false,
  "path": ".",
  "checks": [
    {
      "id": "unsafe-patterns",
      "ok": false,
      "findings": [
        {
          "path": "src/demo/core.py",
          "line": 12,
          "severity": "error",
          "code": "no-type-ignore",
          "message": "Do not use # type: ignore; fix the type flow."
        }
      ]
    }
  ]
}
```

---

## 6.3 `scaffold-guard inspect-diff`

### Command

```bash
scaffold-guard inspect-diff [--path .] [--base main] [--json]
```

### Purpose

Tell a coding agent what obligations apply to the current diff.

### Implementation detail

Use `git diff --name-only BASE...HEAD` if possible.

Fallbacks:

1. `git diff --name-only BASE`
2. `git diff --name-only --cached`
3. `git diff --name-only`
4. clear error if not a git repo.

### V1 diff rules

Implement hardcoded rules first. Later, make them data-driven.

| Changed files | Required action |
|---|---|
| `src/**/*.py` | run Ruff, mypy, Pyright, pytest; require test change |
| `src/**/__init__.py` | run import integration test |
| public API detected by changed `src/**/*.py` | require docs or README change |
| `tests/**/*.py` | run pytest |
| `docs/**/*.md` or `README.md` | run `mkdocs build --strict` and `git diff --check` |
| `pyproject.toml` | run `uv lock` or `uv sync`; require `uv.lock` when lockfile exists |
| `.github/workflows/*.yml` | run YAML lint if available; require manual workflow review |
| `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/**`, `.claude/rules/**` | run `scaffold-guard check`; require rule compilation if source-of-truth changes |
| `examples/**/*.py` | run example smoke test or at least pytest integration if example imported |
| `LICENSE` | no code validation required |
| `.gitignore` | no code validation required unless source/test files also changed |

### Output example

```text
Diff impact summary

Changed areas:
  - package source: src/demo/core.py
  - public docs: README.md

Required validation:
  ✓ uv run ruff format --check .
  ✓ uv run ruff check .
  ✓ uv run mypy src tests
  ✓ uv run pyright
  ✓ uv run pytest --cov=demo --cov-fail-under=95
  ✓ uv run mkdocs build --strict

Required evidence before claiming done:
  - tests changed or added for behavior change
  - docs updated because public source changed
  - final response lists checks run
```

### Acceptance tests

- Source-only diff requires tests and validation.
- Docs-only diff requires docs validation only.
- `pyproject.toml` diff requires lockfile warning.
- Agent-rule diff requires `scaffold-guard check`.
- JSON output is deterministic.

---

## 6.4 `scaffold-guard validate`

### Command

```bash
scaffold-guard validate [--path .] [--quick] [--json]
```

### Purpose

Run the actual validation commands for generated projects.

### Default behavior

Read `scaffold-guard.toml`, then run:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests examples
uv run pyright
uv run mkdocs build --strict
uv run pytest tests --cov=<package_import_name> --cov-report=term-missing --cov-fail-under=<coverage>
scaffold-guard check
```

If `--quick`:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest tests/unit
scaffold-guard check
```

### Implementation requirements

- Use `subprocess.run` without `shell=True`.
- Stream output by default.
- Stop on first failure.
- Return same exit code as failing command, or `1` for policy failure.
- In JSON mode, collect command statuses.

### V1 limitation

Do not support custom command graphs. Use fixed generated-project commands.

---

## 6.5 `scaffold-guard compile-rules`

### Command

```bash
scaffold-guard compile-rules [--path .] [--agent codex|claude|cursor|all] [--dry-run] [--force]
```

### Purpose

Regenerate agent instruction files from templates and `scaffold-guard.toml`.

### Behavior

- Always regenerate `AGENTS.md`.
- Generate `CLAUDE.md` and `.claude/rules/*` only if selected.
- Generate `.cursor/rules/*` only if selected.
- Refuse to overwrite manually edited files unless:
  - `--force` is used; or
  - file contains a generated marker and checksum.

### Generated marker

At the top of generated files, include:

```markdown
<!-- generated by scaffold-guard; edit scaffold-guard.toml or rerun scaffold-guard compile-rules -->
```

For Cursor `.mdc` files, place the marker after frontmatter.

### Checksum

V1 may use a simple marker only. Better: add a footer comment with hash of rendered content excluding the hash line.

Do not overcomplicate if it blocks shipping.

---

## 6.6 `scaffold-guard doctor`

### Command

```bash
scaffold-guard doctor [--path .] [--json]
```

### Checks

- Python version.
- `uv` available.
- `git` available.
- project root detected.
- `pyproject.toml` parseable.
- package import directory exists.
- selected agent files present.
- GitHub Actions workflows present if enabled.
- warning if not inside git repository.

---

## 7. Generated Project Configuration

## 7.1 Generated `pyproject.toml`

Use a strict but workable Python package config.

Template:

```toml
[project]
name = "{{ project_slug }}"
version = "0.1.0"
description = "{{ project_slug }} generated by scaffold-guard."
readme = "README.md"
requires-python = ">={{ python_min }}"
license = "{{ license }}"
dependencies = []

[dependency-groups]
dev = [
    "scaffold-guard>=0.1.0",
    "mkdocs>=1.6.0",
    "mkdocs-material>=9.6.0",
    "mypy>=1.17.0",
    "pytest>=8.4.0",
    "pytest-cov>=6.2.0",
    "pyright>=1.1.400",
    "ruff>=0.12.0",
]

[build-system]
requires = ["hatchling>=1.27.0"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/{{ package_name }}"]

[tool.ruff]
target-version = "py313"
line-length = 100
src = ["src", "tests", "examples"]

[tool.ruff.lint]
select = [
    "ANN",
    "ARG",
    "B",
    "C4",
    "C90",
    "E",
    "F",
    "I",
    "N",
    "PERF",
    "PIE",
    "PL",
    "PT",
    "PTH",
    "RET",
    "RUF",
    "S",
    "SIM",
    "TRY",
    "UP",
]
ignore = [
    "TRY003",
]

[tool.ruff.lint.mccabe]
max-complexity = 10

[tool.ruff.lint.pylint]
max-args = 5
max-branches = 12
max-returns = 6
max-statements = 60

[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = ["S101"]

[tool.mypy]
python_version = "3.13"
strict = true
warn_unreachable = true
pretty = true
show_error_codes = true

[tool.pytest.ini_options]
minversion = "8.4"
testpaths = ["tests"]
pythonpath = ["src"]
addopts = [
    "--strict-config",
    "--strict-markers",
]

[tool.coverage.run]
branch = true
source = ["{{ package_name }}"]

[tool.coverage.report]
fail_under = {{ coverage }}
show_missing = true
skip_covered = true
exclude_also = [
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
]
```

### Notes

- Do not enable pydocstyle in generated projects in V1. It can be too noisy for starters.
- Do include annotation linting.
- Keep generated code fully typed.

---

## 7.2 Generated `pyrightconfig.json`

```json
{
  "include": ["src", "tests", "examples"],
  "exclude": ["**/__pycache__", ".venv", ".mypy_cache", ".pytest_cache", ".ruff_cache"],
  "pythonVersion": "3.13",
  "typeCheckingMode": "strict",
  "venvPath": ".",
  "venv": ".venv",
  "executionEnvironments": [
    {
      "root": ".",
      "extraPaths": ["src"]
    }
  ],
  "reportMissingTypeStubs": "warning"
}
```

---

## 7.3 Generated `scaffold-guard.toml`

```toml
[project]
name = "{{ project_slug }}"
package = "{{ package_name }}"
profile = "python"
python_min = "{{ python_min }}"
coverage_fail_under = {{ coverage }}

[agents]
codex = {{ codex_enabled }}
claude = {{ claude_enabled }}
cursor = {{ cursor_enabled }}

[features]
docs = {{ docs_enabled }}
github_actions = {{ ci_enabled }}
mkdocs = {{ docs_enabled }}

[policy]
forbid_type_ignore = true
forbid_pyright_ignore = true
forbid_noqa = true
forbid_any = true
forbid_dict_str_any = true
forbid_shell_true = true
require_tests_for_src_changes = true
require_docs_for_public_api_changes = true
require_lockfile_for_dependency_changes = true

[validation]
quick = [
  "uv run ruff format --check .",
  "uv run ruff check .",
  "uv run pytest tests/unit",
  "scaffold-guard check"
]
full = [
  "uv run ruff format --check .",
  "uv run ruff check .",
  "uv run mypy src tests examples",
  "uv run pyright",
  "uv run mkdocs build --strict",
  "uv run pytest tests --cov={{ package_name }} --cov-report=term-missing --cov-fail-under={{ coverage }}",
  "scaffold-guard check"
]
```

V1 can parse only the fields it needs. Do not build a universal config framework.

---

## 7.4 Generated GitHub Actions CI

Create `.github/workflows/ci.yml`.

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  python:
    name: Python ${{ matrix.python-version }}
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.13", "3.14"]

    steps:
      - name: Check out repository
        uses: actions/checkout@v7.0.0

      - name: Install uv
        uses: astral-sh/setup-uv@v8.3.0

      - name: Set up Python
        uses: actions/setup-python@v6.3.0
        with:
          python-version: ${{ matrix.python-version }}

      - name: Sync workspace
        run: uv sync --all-groups --python ${{ matrix.python-version }}

      - name: Agent policy check
        run: uv run scaffold-guard check

      - name: Check formatting
        run: uv run ruff format --check .

      - name: Lint
        run: uv run ruff check .

      - name: Type check with mypy
        run: uv run mypy src tests examples

      - name: Type check with Pyright
        run: uv run pyright

      - name: Build docs
        run: uv run mkdocs build --strict

      - name: Test
        run: >
          uv run pytest tests
          --cov={{ package_name }}
          --cov-report=term-missing
          --cov-fail-under={{ coverage }}
```

Create `.github/workflows/docs.yml`.

For V1, make docs workflow build-only by default. Do not deploy Pages unless the user opts in.

```yaml
name: Docs

on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  build:
    name: Build documentation
    runs-on: ubuntu-latest
    steps:
      - name: Check out repository
        uses: actions/checkout@v7.0.0

      - name: Install uv
        uses: astral-sh/setup-uv@v8.3.0

      - name: Set up Python
        uses: actions/setup-python@v6.3.0
        with:
          python-version: "3.13"

      - name: Sync workspace
        run: uv sync --all-groups --python 3.13

      - name: Build docs
        run: uv run mkdocs build --strict
```

### Important

The exact action versions may evolve. V1 tests should not assert specific action versions unless they are part of the template contract.

---

## 8. Generated Agent Instruction Content

## 8.1 `AGENTS.md` sections

Generate a concise but serious root `AGENTS.md`.

Required sections:

```markdown
# Agent Instructions

These rules apply to every code, documentation, and configuration change in this repository.

## Project Orientation
## Working Style
## Python Tooling
## Types and Data Modeling
## Testing Rules
## Documentation Rules
## Security and Secret Handling
## Validation Commands
## Git and Change Hygiene
## Final Response Requirements
## Repository Navigation
```

### Content requirements

Include rules like:

- Use `uv` for dependency management and commands.
- Keep code typed.
- Avoid `Any`.
- Do not use `# type: ignore`, `# pyright: ignore`, or `# noqa` to hide failures.
- Add tests for behavior changes.
- Keep tests deterministic.
- Do not use real network calls in default tests.
- Update docs for public behavior changes.
- Do not commit secrets, `.env`, `.venv`, generated caches, or runtime artifacts.
- Run `scaffold-guard inspect-diff` before final validation when possible.
- Run `scaffold-guard validate` before claiming completion.
- Final response must state:
  - behavior changed;
  - tests added/updated;
  - docs updated or why not;
  - validation commands run;
  - known limitations.

### Keep it short

Target under 250 lines for V1. Avoid bloat.

---

## 8.2 `CLAUDE.md`

Generate:

```markdown
@AGENTS.md

## Claude Code Notes

- Treat `AGENTS.md` as the shared project instruction source.
- Use `.claude/rules/` for path-specific guidance when present.
- Instructions are guidance, not enforcement. Respect `scaffold-guard check` and CI as the source of truth for policy enforcement.
```

Do not duplicate the full `AGENTS.md` content.

---

## 8.3 `.claude/rules/*.md`

Generate five modular files:

### `.claude/rules/python.md`

```markdown
---
paths:
  - "src/**/*.py"
  - "tests/**/*.py"
  - "examples/**/*.py"
---

# Python Rules

- Use `uv run` for Python commands.
- Keep all functions and methods typed.
- Prefer explicit models or typed dictionaries over untyped dictionaries.
- Do not introduce `Any` unless the boundary is genuinely dynamic and tested.
```

### `.claude/rules/testing.md`

```markdown
---
paths:
  - "tests/**/*.py"
  - "src/**/*.py"
---

# Testing Rules

- Add or update tests for every behavior change.
- Prefer deterministic unit tests.
- Do not call live external services in default tests.
- For bug fixes, add a regression test that fails before the fix.
```

### `.claude/rules/docs.md`

```markdown
---
paths:
  - "README.md"
  - "docs/**/*.md"
  - "src/**/*.py"
---

# Documentation Rules

- Update docs when public behavior changes.
- Keep examples runnable.
- Never document future behavior as if it works now.
```

### `.claude/rules/security.md`

```markdown
# Security Rules

- Never commit secrets, `.env`, API keys, private payloads, or local credentials.
- Do not print secrets in tests or examples.
- Prefer explicit dry-run modes for commands that could call external services.
```

### `.claude/rules/git-hygiene.md`

```markdown
# Git Hygiene Rules

- Preserve unrelated user changes.
- Keep diffs focused and reviewable.
- Do not claim work is complete until validation has passed or the blocker is clearly reported.
```

---

## 8.4 `.cursor/rules/*.mdc`

Each Cursor rule must have `.mdc` extension and frontmatter.

### `.cursor/rules/python.mdc`

```markdown
---
description: "Strict Python typing, package layout, and uv workflow rules."
globs: "src/**/*.py, tests/**/*.py, examples/**/*.py"
alwaysApply: false
---

# Python Rules

- Use `uv run` for Python commands.
- Keep all functions, methods, and public constants typed.
- Do not add `Any`, `dict[str, Any]`, type ignores, or broad suppressions.
- Split large modules by responsibility instead of raising lint limits.
```

### `.cursor/rules/testing.mdc`

```markdown
---
description: "Testing expectations for behavior changes and bug fixes."
globs: "src/**/*.py, tests/**/*.py"
alwaysApply: false
---

# Testing Rules

- Add or update tests for every behavior change.
- Prefer deterministic unit tests and explicit regression tests.
- Do not call live external services in default tests.
```

### `.cursor/rules/docs.mdc`

```markdown
---
description: "Documentation requirements for public APIs, commands, and examples."
globs: "README.md, docs/**/*.md, src/**/*.py, examples/**/*.py"
alwaysApply: false
---

# Documentation Rules

- Update README or docs when public behavior changes.
- Keep examples runnable and synchronized with tests.
- Mark unsupported or future behavior honestly.
```

### `.cursor/rules/security.mdc`

```markdown
---
description: "Security and secret handling rules."
alwaysApply: true
---

# Security Rules

- Never commit secrets, `.env`, API keys, credentials, or private payloads.
- Avoid shell commands that delete files outside the project.
- Prefer dry-run behavior for risky actions.
```

### `.cursor/rules/git-hygiene.mdc`

```markdown
---
description: "Git and completion hygiene rules for coding agents."
alwaysApply: true
---

# Git Hygiene Rules

- Preserve unrelated user changes.
- Keep diffs focused.
- Before claiming done, state validation commands and results.
```

---

## 9. Internal Implementation Details

## 9.1 Models

Create `models.py`.

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

AgentChoice = Literal["codex", "claude", "cursor", "all"]
ProfileChoice = Literal["minimal", "python"]
LicenseChoice = Literal["MIT", "Apache-2.0", "none"]


@dataclass(frozen=True)
class InitOptions:
    target_dir: Path
    project_slug: str
    package_name: str
    agent: AgentChoice
    profile: ProfileChoice
    license: LicenseChoice
    python_min: str
    coverage: int
    ci: str
    docs_enabled: bool
    dry_run: bool
    force: bool
```

Create helper properties:

```python
codex_enabled: bool
claude_enabled: bool
cursor_enabled: bool
```

## 9.2 Filesystem safety

Create `fs.py`.

Functions:

```python
def ensure_relative_safe_path(path: str) -> Path: ...
def is_within_directory(base: Path, candidate: Path) -> bool: ...
def write_text_safely(path: Path, content: str, *, force: bool) -> None: ...
def list_created_files(base: Path) -> list[Path]: ...
```

Rules:

- Never write outside target directory.
- Create parent directories as needed.
- Refuse to overwrite unless `force=True`.
- Preserve existing files by default.

## 9.3 Rendering

Create `renderer.py`.

Use Jinja2 with package resources.

Functions:

```python
class TemplateRenderer:
    def render(self, template_name: str, context: Mapping[str, object]) -> str: ...
```

Use `StrictUndefined` so missing variables fail tests.

## 9.4 Scaffold

Create `scaffold.py`.

Responsibilities:

- compute render context;
- build a list of `RenderedFile(path, content)`;
- write or dry-run;
- return summary.

```python
@dataclass(frozen=True)
class RenderedFile:
    path: Path
    content: str
    generated: bool = True
```

## 9.5 Adapters

Create `adapters/base.py`.

```python
class AgentAdapter(Protocol):
    name: str
    def render_files(self, options: InitOptions, renderer: TemplateRenderer) -> list[RenderedFile]: ...
```

Implement:

- `CodexAdapter`: returns no extra files because `AGENTS.md` is base.
- `ClaudeAdapter`: returns `CLAUDE.md` and `.claude/rules/*.md`.
- `CursorAdapter`: returns `.cursor/rules/*.mdc`.

Keep `AGENTS.md` generation in the base Python profile because it is shared.

## 9.6 Checks

Create a common result model.

```python
@dataclass(frozen=True)
class Finding:
    path: Path
    line: int | None
    severity: Literal["error", "warning"]
    code: str
    message: str

@dataclass(frozen=True)
class CheckResult:
    id: str
    ok: bool
    findings: list[Finding]
```

Each checker implements:

```python
class Checker(Protocol):
    id: str
    def run(self, project_root: Path) -> CheckResult: ...
```

## 9.7 Diffing

Create `diffing.py`.

Functions:

```python
def get_changed_files(project_root: Path, base: str) -> list[Path]: ...
def classify_changed_files(files: list[Path]) -> DiffImpact: ...
def required_actions(impact: DiffImpact) -> list[RequiredAction]: ...
```

Use `subprocess.run(["git", ...], shell=False)`.

---

## 10. Tests

## 10.1 Test commands for CLI package

The implementation repo itself must pass:

```bash
uv sync --all-groups
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pyright
uv run pytest tests --cov=scaffold_guard --cov-report=term-missing --cov-fail-under=95
uv run mkdocs build --strict
```

## 10.2 Unit test list

Create tests for:

### CLI init

- `test_init_codex_creates_agents_only`
- `test_init_claude_creates_claude_wrapper`
- `test_init_cursor_creates_mdc_rules`
- `test_init_all_creates_all_adapters`
- `test_init_dry_run_writes_nothing`
- `test_init_rejects_path_traversal`
- `test_init_existing_dir_requires_force`

### Renderer

- `test_renderer_raises_on_missing_context`
- `test_renderer_loads_packaged_templates`
- `test_no_unresolved_jinja_in_rendered_files`

### Adapters

- `test_codex_adapter_has_no_extra_files`
- `test_claude_adapter_imports_agents_md`
- `test_cursor_rules_have_frontmatter`

### Checks

- `test_unsafe_patterns_detects_type_ignore`
- `test_unsafe_patterns_detects_pyright_ignore`
- `test_unsafe_patterns_detects_dict_str_any`
- `test_unsafe_patterns_detects_shell_true`
- `test_project_health_requires_agents_md`
- `test_project_health_validates_claude_import`
- `test_project_health_validates_cursor_mdc`
- `test_generated_files_detects_unresolved_placeholders`

### Diff

- `test_inspect_diff_source_requires_tests_docs_validation`
- `test_inspect_diff_docs_requires_mkdocs`
- `test_inspect_diff_pyproject_requires_lockfile`
- `test_inspect_diff_agent_rules_requires_scaffold_guard_check`

## 10.3 Integration tests

Use temporary directories.

### Generated package smoke

1. Run `scaffold-guard init demo --agent all`.
2. Assert generated tree exists.
3. Run `scaffold-guard check --path demo`.
4. Optionally run:
   - `uv sync --all-groups`;
   - `uv run ruff format --check .`;
   - `uv run ruff check .`;
   - `uv run mypy src tests examples`;
   - `uv run pyright`;
   - `uv run pytest`.

To avoid slow tests on every run, mark full generated-project validation as integration.

### Compile rules idempotence

1. Generate project.
2. Run `scaffold-guard compile-rules`.
3. Assert no content changes.

### JSON mode

Assert `check --json` and `inspect-diff --json` produce valid JSON.

---

## 11. Documentation

Create docs for the CLI package:

```text
docs/index.md
docs/quickstart.md
docs/adapters.md
docs/generated-project.md
docs/checks.md
docs/releasing.md
```

## 11.1 `README.md`

Must include:

- what the tool does;
- installation with `uv tool install scaffold-guard`;
- examples for Codex, Claude, Cursor, all;
- generated tree;
- commands after generation;
- limitations;
- roadmap.

Example:

```markdown
# scaffold-guard

Generate strict starter repositories for coding agents.

```bash
uv tool install scaffold-guard
scaffold-guard init my_project --agent all
cd my_project
scaffold-guard validate
```
```

## 11.2 `docs/adapters.md`

Explain:

- Codex adapter: `AGENTS.md` first-class;
- Claude adapter: `CLAUDE.md` imports `AGENTS.md`;
- Cursor adapter: `.cursor/rules/*.mdc` plus `AGENTS.md`;
- why instructions are not enough and policy checks matter.

## 11.3 `docs/checks.md`

Document each checker and exit code.

## 11.4 `docs/releasing.md`

Document manual PyPI release process for the package itself:

```bash
uv sync --all-groups
uv run scaffold-guard validate
uv build
uv publish
```

Add a note: Homebrew formula is planned after PyPI install is stable.

---

## 12. V1 Milestones and Task Breakdown

## Milestone 0: Bootstrap the package repository

### Tasks

- [ ] Create `pyproject.toml`.
- [ ] Add `src/scaffold_guard/__init__.py`.
- [ ] Add `src/scaffold_guard/__main__.py`.
- [ ] Add `src/scaffold_guard/cli.py` with Typer app and placeholder commands.
- [ ] Add Ruff, mypy, Pyright, pytest, coverage config.
- [ ] Add initial tests for `scaffold-guard version`.
- [ ] Add CI for the CLI package itself.

### Acceptance criteria

- `uv run scaffold-guard version` works.
- `uv run pytest` passes.
- Ruff/mypy/Pyright pass on placeholder package.

---

## Milestone 1: Implement template rendering and filesystem-safe writes

### Tasks

- [ ] Implement `TemplateRenderer`.
- [ ] Implement `RenderedFile`.
- [ ] Implement safe path helpers.
- [ ] Package one trivial template.
- [ ] Test packaged template loading.
- [ ] Test dry-run behavior.
- [ ] Test overwrite protection.

### Acceptance criteria

- Template rendering fails on missing variables.
- No write can escape the target directory.
- Existing files are preserved unless `--force`.

---

## Milestone 2: Implement `init` for the `minimal` and `python` profiles

### Tasks

- [ ] Implement name validation.
- [ ] Implement package name conversion.
- [ ] Render base project files.
- [ ] Render GitHub Actions.
- [ ] Render minimal guardrails by default.
- [ ] Render package docs and tests when `--profile python` is selected.
- [ ] Render `scaffold-guard.toml`.
- [ ] Add CLI output summary.

### Acceptance criteria

- `scaffold-guard init demo --agent codex` produces a valid minimal tree.
- `scaffold-guard init demo --profile python --agent codex` produces a valid package tree.
- Python-profile generated source imports.
- Python-profile generated tests are syntactically valid.
- Generated files have no unresolved placeholders.

---

## Milestone 3: Implement agent adapters

### Tasks

- [ ] Implement `CodexAdapter`.
- [ ] Implement `ClaudeAdapter`.
- [ ] Implement `CursorAdapter`.
- [ ] Add adapter selection logic.
- [ ] Add adapter tests.
- [ ] Ensure `AGENTS.md` always exists.

### Acceptance criteria

- `--agent codex` creates only `AGENTS.md` for agent files.
- `--agent claude` creates `CLAUDE.md` importing `AGENTS.md`.
- `--agent cursor` creates valid `.cursor/rules/*.mdc`.
- `--agent all` creates all files.

---

## Milestone 4: Implement `check`

### Tasks

- [ ] Implement checker result models.
- [ ] Implement `unsafe-patterns`.
- [ ] Implement `project-health`.
- [ ] Implement `generated-files`.
- [ ] Implement `config-consistency`.
- [ ] Add text output.
- [ ] Add JSON output.
- [ ] Add exit codes.

### Acceptance criteria

- `scaffold-guard check` passes in a freshly generated project.
- Introducing `# type: ignore` causes failure.
- Removing `AGENTS.md` causes failure.
- Invalid `.cursor/rules/foo.md` causes failure.
- JSON output is parseable.

---

## Milestone 5: Implement `inspect-diff`

### Tasks

- [ ] Implement git changed-file collection.
- [ ] Implement diff classification.
- [ ] Implement required action mapping.
- [ ] Add text output.
- [ ] Add JSON output.
- [ ] Add tests using temporary git repositories.

### Acceptance criteria

- Source changes require tests and validation.
- Docs changes require docs validation.
- Agent rules changes require `scaffold-guard check`.
- `pyproject.toml` changes warn about lockfile.
- Works when there are staged but uncommitted changes.

---

## Milestone 6: Implement `validate`, `doctor`, and `compile-rules`

### Tasks

- [ ] Implement `doctor`.
- [ ] Implement `validate --quick`.
- [ ] Implement full `validate`.
- [ ] Implement `compile-rules`.
- [ ] Add idempotence tests.
- [ ] Add JSON output where appropriate.

### Acceptance criteria

- `scaffold-guard doctor` reports useful environment status.
- `scaffold-guard validate --quick` runs without shell=True.
- `compile-rules` regenerates agent files and is idempotent.
- Existing manual files are not overwritten without `--force`.

---

## Milestone 7: Documentation and release readiness

### Tasks

- [ ] Complete README.
- [ ] Complete docs.
- [ ] Add examples in README.
- [ ] Add changelog.
- [ ] Add manual release checklist.
- [ ] Build wheel and inspect included templates.
- [ ] Test package install from local wheel.

### Acceptance criteria

- `uv build` succeeds.
- Wheel includes templates.
- Local wheel install exposes `scaffold-guard`.
- `mkdocs build --strict` passes.
- A user can follow README quickstart.

---

## 13. Acceptance Criteria for V1 Release

V1 is done when all of the following are true:

1. `scaffold-guard init demo --agent all` creates a complete project.
2. The generated project passes `scaffold-guard check`.
3. The generated project can run:
   ```bash
   uv sync --all-groups
   uv run scaffold-guard validate --quick
   ```
4. Adapter-specific generated files are correct:
   - Codex: `AGENTS.md`;
   - Claude: `CLAUDE.md` imports `AGENTS.md`;
   - Cursor: `.cursor/rules/*.mdc` with frontmatter.
5. `scaffold-guard inspect-diff` produces useful required-validation guidance.
6. The CLI package test suite passes:
   ```bash
   uv run ruff format --check .
   uv run ruff check .
   uv run mypy src tests
   uv run pyright
   uv run pytest tests --cov=scaffold_guard --cov-report=term-missing --cov-fail-under=95
   uv run mkdocs build --strict
   ```
7. README has working quickstart instructions.
8. Built wheel includes all templates.
9. No tests require network access.
10. No secrets, generated caches, or local virtual environments are committed.

---

## 14. V1.1 / V2 Roadmap

Do not implement these until V1 is shipped.

### V1.1

- Codex hooks starter:
  - `.codex/hooks/pre_tool_use_policy.py`
  - optional hook config examples
- Claude hooks starter:
  - `.claude/settings.json`
  - `PreToolUse` command blocker
- pre-commit integration
- allow comments for policy checker exceptions
- `scaffold-guard upgrade` to apply starter updates to existing generated repos
- richer `scaffold-guard.toml` diff rules

### V2

- `fastapi` profile
- `agent-app` profile
- `rag` profile
- `mcp-server` profile
- `evals` profile
- TestPyPI release rehearsal for generated packages
- Homebrew formula
- GitHub Action for `scaffold-guard check`
- `agent-rulespec` package split
- plugin system for custom rules

### V3

- release/CD gatekeeper:
  - semantic version checks;
  - changelog checks;
  - package provenance;
  - trusted publishing;
  - smoke install;
  - post-release verification;
  - rollback checklist.

---

## 15. Coding Agent Instructions for Implementing This Plan

When implementing:

1. Make the smallest complete V1.
2. Do not build future roadmap items early.
3. Keep implementation files focused and under roughly 300 lines when practical.
4. Prefer standard library over dependencies unless a dependency clearly simplifies CLI UX.
5. Do not use `shell=True`.
6. Do not write outside temporary directories in tests.
7. Do not add network-dependent tests.
8. Keep generated templates deterministic.
9. Add tests for every behavior.
10. Update README/docs in the same change as CLI behavior.

Before claiming completion, run:

```bash
uv sync --all-groups
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pyright
uv run pytest tests --cov=scaffold_guard --cov-report=term-missing --cov-fail-under=95
uv run mkdocs build --strict
```

Final response must include:

- implementation summary;
- files changed;
- tests added;
- validation commands run;
- known limitations;
- whether roadmap items were intentionally deferred.

---

## 16. Suggested Initial Prompt to Give a Coding Agent

Use this prompt after placing this plan in the repository:

```text
Implement V1 of scaffold-guard according to docs/V1_IMPLEMENTATION_PLAN.md.

Start with Milestone 0 through Milestone 3 only:
- package bootstrap;
- template renderer;
- filesystem-safe init command;
- Python profile templates;
- Codex, Claude, and Cursor adapters.

Do not implement hooks, Homebrew, FastAPI/RAG/MCP profiles, telemetry, or CD.

Add tests for every implemented behavior.
Keep generated files deterministic.
Run the validation commands listed in the plan before claiming completion.
```

After Milestone 3 passes, continue with:

```text
Continue implementing docs/V1_IMPLEMENTATION_PLAN.md from Milestone 4 through Milestone 6:
- scaffold-guard check;
- inspect-diff;
- validate;
- doctor;
- compile-rules.

Do not expand scope beyond V1.
```

Then:

```text
Finish V1 release readiness from Milestone 7:
- README;
- docs;
- release checklist;
- wheel package-data verification;
- integration tests for generated project.

Do not publish to PyPI yet.
```

---

## 17. Source Notes for Maintainers

These sources were checked while drafting the plan:

- Codex AGENTS.md docs: https://developers.openai.com/codex/guides/agents-md
- Codex hooks docs: https://developers.openai.com/codex/hooks
- Claude Code memory / CLAUDE.md docs: https://code.claude.com/docs/en/memory
- Cursor rules docs: https://cursor.com/docs/rules.md

Keep these links in the docs but avoid hard-coding implementation to unstable vendor internals beyond the generated file formats.
