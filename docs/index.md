# RepoGuard

`repo-guard` creates strict Python starter repositories for coding-agent
workflows. The generated project includes typed package defaults, `uv` commands,
GitHub Actions CI, local policy checks, and agent instruction files.

## What V1 Provides

- `repo-guard init` for package-style Python repositories.
- `AGENTS.md` for Codex and shared cross-agent guidance.
- `CLAUDE.md` plus `.claude/rules/*.md` when Claude Code is selected.
- `.cursor/rules/*.mdc` when Cursor is selected.
- `repo-guard check` for fast local policy checks.
- `repo-guard inspect-diff` for diff-specific validation guidance.
- `repo-guard validate`, `compile-rules`, `doctor`, and `version`.

## Basic Flow

```bash
uvx agent-ready-python init my_project --agent all
cd my_project
uv sync --all-groups
uv run repo-guard check
uv run repo-guard validate --quick
```

Read the quickstart first, then use the adapter and checks pages when tuning a
generated project.
