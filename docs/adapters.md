# Agent Adapters

## Codex

Codex uses `AGENTS.md` as the generated shared instruction file. The `codex`
adapter creates no additional agent files because the base scaffold always
includes `AGENTS.md`.

## Claude Code

Claude Code reads `CLAUDE.md`, so the Claude adapter creates a small wrapper
that references `AGENTS.md` and adds Claude-specific notes. It also creates
`.claude/rules/*.md` files for path-oriented guidance.

`CLAUDE.md` does not duplicate the full shared instructions. `AGENTS.md` remains
the shared source of truth.

## Cursor

Cursor support creates `.cursor/rules/*.mdc` files plus the shared `AGENTS.md`.
Each `.mdc` file includes frontmatter with metadata such as `description`,
`alwaysApply`, and `globs` where appropriate.

## Why Checks Still Matter

Instruction files guide agents, but they do not enforce behavior. Generated
projects use `agent-safe check`, strict local tooling, and GitHub Actions CI to
catch risky patterns such as type suppressions, unresolved templates, missing
adapter files, and mismatched configuration.
