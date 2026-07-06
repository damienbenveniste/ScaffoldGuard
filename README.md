# agent-safe-python

`agent-safe-python` generates strict Python starter repositories for teams using
coding agents. It creates a typed package layout, local validation commands,
GitHub Actions workflows, and agent instructions for Codex, Claude Code, and
Cursor.

The installed command is `agent-safe`.

## Install

After the package is published to PyPI:

```bash
uvx agent-safe-python version
```

From a local checkout or built wheel:

```bash
uv sync --all-groups
uv run agent-safe version
uv build
uvx --from dist/agent_safe_python-0.1.0-py3-none-any.whl agent-safe version
```

## Quickstart

Generate a project with every supported adapter:

```bash
uvx agent-safe-python init my_project --agent all
cd my_project
uv sync --all-groups
uv run agent-safe check
uv run agent-safe validate --quick
```

Generate for one agent surface:

```bash
uvx agent-safe-python init codex_demo --agent codex
uvx agent-safe-python init claude_demo --agent claude
uvx agent-safe-python init cursor_demo --agent cursor
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
  agent-safe.toml
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
agent-safe init NAME [--agent codex|claude|cursor|all]
agent-safe check [--path .] [--json]
agent-safe inspect-diff [--path .] [--base main] [--json]
agent-safe validate [--path .] [--quick] [--json]
agent-safe compile-rules [--path .] [--agent codex|claude|cursor|all] [--dry-run] [--force]
agent-safe doctor [--path .] [--json]
agent-safe version
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
uv run pytest tests --cov=agent_safe --cov-report=term-missing --cov-fail-under=95
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
