# Quickstart

## Install

```bash
uv tool install scaffold-guard
scaffold-guard version
```

## Create A Project

Start the guided setup and answer the prompts. This example assumes you enter
`my_project` as the project name and keep the default `minimal` profile.

```bash
scaffold-guard init
cd my_project
scaffold-guard check
scaffold-guard validate --quick
```

Use the [command reference](commands.md) for the full CLI surface, including
`inspect-diff`, `validate`, `compile-rules`, `doctor`, and `version`.

Profile choices:

| Profile | Meaning |
|---|---|
| `minimal` | Guardrails only; no Python or TypeScript source scaffold |
| `python` | Python package scaffold with `src/`, tests, docs, and `uv` |
| `typescript` | TypeScript package scaffold with npm and configurable TypeScript tooling |
| `monorepo` | Python + TypeScript workspaces under `packages/` |

Generated projects include CI and local development defaults, but the
user-facing CLI remains the installed `scaffold-guard` command.

For non-interactive use with defaults, pass the options as flags:

```bash
scaffold-guard init my_project --agent all
```

If you already created and entered a project folder, run the same guided setup
command from that folder. Press Enter at the project-name prompt to use the
current directory. Existing unrelated files are preserved; if a generated
destination such as `README.md` already exists, ScaffoldGuard stops unless you
rerun with `--force`.

```bash
scaffold-guard init
```

Use one adapter when you only need one agent surface:

```bash
scaffold-guard init codex_demo --agent codex
scaffold-guard init claude_demo --agent claude
scaffold-guard init cursor_demo --agent cursor
```

Use GitLab CI instead of GitHub Actions:

```bash
scaffold-guard init gitlab_demo --ci gitlab
```

Use the `python` profile when you want a full Python package layout. Guided
setup asks for Ruff linting strictness, Python type-checking strictness, and the
Python type checker. Strict Ruff plus mypy and Pyright are enabled by default,
but Ruff and type checking can each be set to `standard` or `off`.

```bash
scaffold-guard init python_demo --guided
cd python_demo
uv sync --all-groups
scaffold-guard validate --quick
```

Use the `typescript` profile when you want a TypeScript package with npm
scripts. Strict compiler mode, Biome, and Vitest are enabled by default and can
be changed during guided setup or with flags:

```bash
scaffold-guard init ts_demo --profile typescript
cd ts_demo
npm install
scaffold-guard validate --quick
```

Use the `monorepo` profile when Python and TypeScript should live in one
repository. Guided setup asks for both Python and TypeScript tool choices:

```bash
scaffold-guard init app_demo --profile monorepo
cd app_demo
uv sync --all-groups
npm install
scaffold-guard validate --quick
```

## Preview Or Refresh Files

Preview a new project without writing files:

```bash
scaffold-guard init demo --dry-run
```

Refresh managed instruction files from inside a generated project:

```bash
scaffold-guard compile-rules --dry-run
scaffold-guard compile-rules --force
```

`compile-rules` refuses to overwrite manually edited instruction files unless
`--force` is supplied or the file has the generated marker.
