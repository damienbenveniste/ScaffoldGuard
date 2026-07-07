# ScaffoldGuard

`scaffold-guard` creates strict starter repositories for coding-agent workflows.
The default `minimal` profile adds agent guardrails, GitHub Actions CI, local
policy checks, and agent instruction files without forcing a Python package
layout. The `package` profile adds typed Python package defaults.

## What V1 Provides

- `scaffold-guard init` for minimal guardrails or package-style Python repositories.
- `AGENTS.md` for Codex and shared cross-agent guidance.
- `CLAUDE.md` plus `.claude/rules/*.md` when Claude Code is selected.
- `.cursor/rules/*.mdc` when Cursor is selected.
- `scaffold-guard check` for fast local policy checks.
- `scaffold-guard inspect-diff` for diff-specific validation guidance.
- `scaffold-guard validate`, `compile-rules`, `doctor`, and `version`.

## Basic Flow

This example assumes you enter `my_project` as the project name during guided
setup and keep the default `minimal` profile.

```bash
uv tool install scaffold-guard
scaffold-guard init
cd my_project
scaffold-guard check
scaffold-guard validate --quick
```

The `init` command starts guided setup when `NAME` is omitted. Leave the
project-name prompt blank to initialize the current empty folder, or enter a
name to create a new project directory. Choose `package` when you want
`src/`, tests, docs, and Python tooling. Package guided setup asks whether to
enable Ruff, mypy, and Pyright; all three default to enabled. Pass `NAME` and
flags for non-interactive use with defaults.

Generated projects include CI and local development defaults, but the
user-facing CLI remains the installed `scaffold-guard` command.

Read the quickstart first, then use the adapter and checks pages when tuning a
generated project.
