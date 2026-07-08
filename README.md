# ScaffoldGuard

`scaffold-guard` generates strict starter repositories for teams using coding
agents. It creates local validation commands, GitHub Actions workflows or
GitLab CI pipelines, and agent instructions for Codex, Claude Code, and Cursor.
The default `minimal` profile adds guardrails only. The `python`,
`typescript`, and `monorepo` profiles add Python, TypeScript, or mixed
Python+TypeScript starter layouts.

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

For non-interactive use with defaults, pass the options as flags:

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

Choose GitLab CI instead of GitHub Actions when needed:

```bash
scaffold-guard init gitlab_demo --ci gitlab
```

Generate a full Python package scaffold when you want source, tests, docs, and
package tooling. Guided setup lets you keep or disable Ruff, mypy, and Pyright;
all three are enabled by default.

```bash
scaffold-guard init python_demo --guided
cd python_demo
uv sync --all-groups
scaffold-guard validate --quick
```

Generate a TypeScript package when you want npm scripts and configurable
TypeScript tooling. Strict compiler mode, Biome, and Vitest are enabled by
default and can be changed during guided setup or with flags:

```bash
scaffold-guard init ts_demo --profile typescript
cd ts_demo
npm install
scaffold-guard validate --quick
```

Generate a Python + TypeScript monorepo when you want both language workspaces
managed from one repository:

```bash
scaffold-guard init app_demo --profile monorepo
cd app_demo
uv sync --all-groups
npm install
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
  .github/workflows/ci.yml  # or .gitlab-ci.yml
```

The `python` profile adds a Python package scaffold:

```text
my_project/
  AGENTS.md
  README.md
  LICENSE
  pyproject.toml
  pyrightconfig.json  # when Pyright is enabled
  scaffold-guard.toml
  .github/workflows/  # or .gitlab-ci.yml
  docs/
  examples/
  src/my_project/
  tests/unit/
  tests/integration/
```

The `typescript` profile adds a TypeScript package scaffold with configurable
compiler strictness, Biome, and Vitest defaults:

```text
my_project/
  AGENTS.md
  README.md
  LICENSE
  package.json
  tsconfig.json
  tsconfig.build.json
  biome.json  # when Biome is enabled
  vitest.config.ts  # when Vitest is enabled
  scaffold-guard.toml
  .github/workflows/ci.yml  # or .gitlab-ci.yml
  src/
  tests/  # when Vitest is enabled
```

The `monorepo` profile adds Python and TypeScript workspaces:

```text
my_project/
  AGENTS.md
  README.md
  LICENSE
  pyproject.toml
  package.json
  biome.json  # when Biome is enabled
  pyrightconfig.json  # when Pyright is enabled
  scaffold-guard.toml
  .github/workflows/ci.yml  # or .gitlab-ci.yml
  packages/python/
  packages/typescript/
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
scaffold-guard init [NAME] [--guided] [--profile minimal|python|typescript|monorepo] [--agent codex|claude|cursor|all] [--ci github|gitlab] [--ruff strict|off] [--python-typecheck mypy+pyright|mypy|pyright|off] [--typescript-mode strict|standard] [--typescript-lint biome|off] [--typescript-test vitest|off]
scaffold-guard check [--path .] [--json]
scaffold-guard inspect-diff [--path .] [--base main] [--json]
scaffold-guard validate [--path .] [--quick] [--json]
scaffold-guard compile-rules [--path .] [--agent codex|claude|cursor|all] [--dry-run] [--force]
scaffold-guard doctor [--path .] [--json]
scaffold-guard version
```

Profile choices:

| Profile | Meaning |
|---|---|
| `minimal` | Guardrails only; no Python or TypeScript source scaffold |
| `python` | Python package scaffold with `src/`, tests, docs, and `uv` |
| `typescript` | TypeScript package scaffold with npm and configurable TypeScript tooling |
| `monorepo` | Python + TypeScript workspaces under `packages/` |

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
