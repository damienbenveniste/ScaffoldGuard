# ScaffoldGuard

`scaffold-guard` creates strict Python starter repositories for coding-agent
workflows. The generated project includes typed package defaults, `uv` commands,
GitHub Actions CI, local policy checks, and agent instruction files.

## What V1 Provides

- `scaffold-guard init` for package-style Python repositories.
- `AGENTS.md` for Codex and shared cross-agent guidance.
- `CLAUDE.md` plus `.claude/rules/*.md` when Claude Code is selected.
- `.cursor/rules/*.mdc` when Cursor is selected.
- `scaffold-guard check` for fast local policy checks.
- `scaffold-guard inspect-diff` for diff-specific validation guidance.
- `scaffold-guard validate`, `compile-rules`, `doctor`, and `version`.

## Basic Flow

This example assumes you enter `my_project` as the project name during guided
setup.

```bash
uv tool install scaffold-guard
scaffold-guard init
cd my_project
uv sync --all-groups
scaffold-guard check
scaffold-guard validate --quick
```

The `init` command starts guided setup when `NAME` is omitted. Leave the
project-name prompt blank to initialize the current empty folder, or enter a
name to create a new project directory. Pass `NAME` and flags for
non-interactive use.

Generated projects include CI and local development defaults, but the
user-facing CLI remains the installed `scaffold-guard` command.

Read the quickstart first, then use the adapter and checks pages when tuning a
generated project.
