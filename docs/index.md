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

```bash
uv tool install scaffold-guard
scaffold-guard init my_project --agent all
cd my_project
uv sync --all-groups
uv run scaffold-guard check
uv run scaffold-guard validate --quick
```

Generated projects include `scaffold-guard` in the `dev` dependency group, so
use `uv run scaffold-guard ...` inside the project after
`uv sync --all-groups`.

Read the quickstart first, then use the adapter and checks pages when tuning a
generated project.
