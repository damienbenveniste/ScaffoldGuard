# agent-safe-python

`agent-safe-python` creates strict Python starter repositories for coding-agent
workflows. The generated project includes typed package defaults, `uv` commands,
GitHub Actions CI, local policy checks, and agent instruction files.

## What V1 Provides

- `agent-safe init` for package-style Python repositories.
- `AGENTS.md` for Codex and shared cross-agent guidance.
- `CLAUDE.md` plus `.claude/rules/*.md` when Claude Code is selected.
- `.cursor/rules/*.mdc` when Cursor is selected.
- `agent-safe check` for fast local policy checks.
- `agent-safe inspect-diff` for diff-specific validation guidance.
- `agent-safe validate`, `compile-rules`, `doctor`, and `version`.

## Basic Flow

```bash
uvx agent-safe-python init my_project --agent all
cd my_project
uv sync --all-groups
uv run agent-safe check
uv run agent-safe validate --quick
```

Read the quickstart first, then use the adapter and checks pages when tuning a
generated project.
