# ScaffoldGuard

`scaffold-guard` generates strict starter repositories for teams using coding
agents. It creates local validation commands, GitHub Actions workflows, and
agent instructions for Codex, Claude Code, and Cursor. The default `minimal`
profile adds guardrails only; the `package` profile adds a typed Python package
layout.

The PyPI package is `scaffold-guard`; the installed command is
`scaffold-guard`.

Documentation: <https://damienbenveniste.github.io/ScaffoldGuard/>

## Install

```bash
uv tool install scaffold-guard
scaffold-guard version
```

## Publishing

Maintainers publish `scaffold-guard` through GitHub Actions Trusted Publishing.
No PyPI API token is required. To release a new version, create a GitHub Release
or manually run the `Publish` workflow from `main`.

## Contributing

Issues and pull requests are welcome. Read
[CONTRIBUTING.md](CONTRIBUTING.md) before opening a change.

Please report security issues privately through
[SECURITY.md](SECURITY.md), not in public issues.

## Quickstart

Start the guided setup and answer the prompts. This example assumes you enter
`my_project` as the project name and keep the default `minimal` profile.

```bash
scaffold-guard init
cd my_project
scaffold-guard check
scaffold-guard validate --quick
```

Generated projects include CI and local development defaults, but the user-facing
CLI remains the installed `scaffold-guard` command.

For non-interactive use, pass the options as flags:

```bash
scaffold-guard init my_project --agent all
```

If you already created and entered an empty project folder, run the same guided
setup command from that folder. Press Enter at the project-name prompt to use
the current directory:

```bash
scaffold-guard init
```

Generate for one agent surface:

```bash
scaffold-guard init codex_demo --agent codex
scaffold-guard init claude_demo --agent claude
scaffold-guard init cursor_demo --agent cursor
```

Generate a full Python package scaffold when you want source, tests, docs, and
package tooling:

```bash
scaffold-guard init package_demo --profile package --agent all
cd package_demo
uv sync --all-groups
scaffold-guard validate --quick
```

Use `--dry-run` to preview files and `--force` to overwrite known generated
files.

## Generated Project

The default `minimal` profile creates guardrails only:

```text
my_project/
  AGENTS.md
  README.md
  LICENSE
  scaffold-guard.toml
  .github/workflows/ci.yml
```

The `package` profile adds a Python package scaffold:

```text
my_project/
  AGENTS.md
  README.md
  LICENSE
  pyproject.toml
  pyrightconfig.json
  scaffold-guard.toml
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
scaffold-guard init [NAME] [--guided] [--profile minimal|package] [--agent codex|claude|cursor|all]
scaffold-guard check [--path .] [--json]
scaffold-guard inspect-diff [--path .] [--base main] [--json]
scaffold-guard validate [--path .] [--quick] [--json]
scaffold-guard compile-rules [--path .] [--agent codex|claude|cursor|all] [--dry-run] [--force]
scaffold-guard doctor [--path .] [--json]
scaffold-guard version
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
uv run pytest tests --cov=scaffold_guard --cov-report=term-missing --cov-fail-under=95
uv run mkdocs build --strict
uv build
```

## Limitations

V1 is a developer CLI, not a SaaS product or policy server. It does not include
telemetry, external AI calls, Codex or Claude hooks, a plugin system, Homebrew
automation, or automatic upgrades for mature existing repositories.

Homebrew distribution, hook starter templates, more specialized project profiles, and richer
policy configuration are intentionally deferred until after the PyPI package is
stable.
