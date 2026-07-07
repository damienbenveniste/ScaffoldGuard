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

Profile choices:

| Profile | Meaning |
|---|---|
| `minimal` | Guardrails only; no Python or TypeScript source scaffold |
| `package` | Python package scaffold with `src/`, tests, docs, and `uv` |
| `typescript` | TypeScript package scaffold with npm, Biome, and Vitest |
| `monorepo` | Python + TypeScript workspaces under `packages/` |

Generated projects include CI and local development defaults, but the
user-facing CLI remains the installed `scaffold-guard` command.

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

Use the `package` profile when you want a full Python package layout. Guided
setup lets you keep or disable Ruff, mypy, and Pyright; all three are enabled
by default.

```bash
scaffold-guard init package_demo --guided
cd package_demo
uv sync --all-groups
scaffold-guard validate --quick
```

Use the `typescript` profile when you want a strict TypeScript package with
npm scripts, TypeScript, Biome, and Vitest:

```bash
scaffold-guard init ts_demo --profile typescript
cd ts_demo
npm install
scaffold-guard validate --quick
```

Use the `monorepo` profile when Python and TypeScript should live in one
repository:

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
