# RepoGuard

`repo-guard` generates strict Python starter repositories for teams using
coding agents. It creates a typed package layout, local validation commands,
GitHub Actions workflows, and agent instructions for Codex, Claude Code, and
Cursor.

The PyPI package and installed command are both `repo-guard`.

## Install

After the package is published to PyPI:

```bash
uvx repo-guard version
```

From a local checkout or built wheel:

```bash
uv sync --all-groups
uv run repo-guard version
uv build
uvx --from dist/repo_guard-0.1.0-py3-none-any.whl repo-guard version
```

## Publishing

PyPI publishing is prepared through GitHub Actions Trusted Publishing. Before
the first release, configure a PyPI pending publisher for:

```text
Project name: repo-guard
Owner: damienbenveniste
Repository: RepoGuard
Workflow: publish.yml
Environment: pypi
```

No PyPI API token is required. After the pending publisher exists, publish a
GitHub Release or manually run the `Publish` workflow from `main`.

## Quickstart

Generate a project with every supported adapter:

```bash
uvx repo-guard init my_project --agent all
cd my_project
uv sync --all-groups
uv run repo-guard check
uv run repo-guard validate --quick
```

Generate for one agent surface:

```bash
uvx repo-guard init codex_demo --agent codex
uvx repo-guard init claude_demo --agent claude
uvx repo-guard init cursor_demo --agent cursor
```

Use `--dry-run` to preview files and `--force` to overwrite known generated
files.

## Generated Project

The default `package` profile creates:

```text
my_project/
  AGENTS.md
  README.md
  LICENSE
  pyproject.toml
  pyrightconfig.json
  repo-guard.toml
  .github/workflows/
  docs/
  examples/
  src/my_project/
  tests/unit/
  tests/integration/
```

Adapter files are added according to `--agent`:

| Agent | Generated instruction files |
|---|---|
| `codex` | `AGENTS.md` |
| `claude` | `AGENTS.md`, `CLAUDE.md`, `.claude/rules/*.md` |
| `cursor` | `AGENTS.md`, `.cursor/rules/*.mdc` |
| `all` | all of the above |

## Commands

```bash
repo-guard init NAME [--agent codex|claude|cursor|all]
repo-guard check [--path .] [--json]
repo-guard inspect-diff [--path .] [--base main] [--json]
repo-guard validate [--path .] [--quick] [--json]
repo-guard compile-rules [--path .] [--agent codex|claude|cursor|all] [--dry-run] [--force]
repo-guard doctor [--path .] [--json]
repo-guard version
```

`check` runs fast policy checks. `inspect-diff` explains validation obligations
for changed files in a git repository. `validate` runs the generated project's
configured validation gate. `compile-rules` regenerates managed agent
instruction files from templates. `doctor` reports local tool and generated
project health.

## Local Development

Run the package gate from this repository:

```bash
uv sync --all-groups --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pyright
uv run pytest tests --cov=repo_guard --cov-report=term-missing --cov-fail-under=95
uv run mkdocs build --strict
uv build
```

## Limitations

V1 is a developer CLI, not a SaaS product or policy server. It does not include
telemetry, external AI calls, Codex or Claude hooks, a plugin system, Homebrew
automation, or automatic upgrades for mature existing repositories.

Homebrew distribution, hook starter templates, more project profiles, and richer
policy configuration are intentionally deferred until after the PyPI package is
stable.
