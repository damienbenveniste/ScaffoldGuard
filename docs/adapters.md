# Agent Adapters

## Codex

Codex uses a layered project adapter:

- `AGENTS.md` defines shared behavior and repository operating rules.
- `.codex/config.toml` sets project mode and permissions after the project is
  trusted.
- `.codex/rules/*.rules` defines allowed, prompted, and forbidden command
  prefixes.
- `.codex/hooks.json` runs generated checks around tool use.

The `codex` adapter currently generates `.codex/rules/git.rules` and
`.codex/rules/validation.rules`.

## Claude Code

Claude Code reads `CLAUDE.md`, so the Claude adapter creates a small wrapper
that references `AGENTS.md` and adds Claude-specific notes. It also creates
`.claude/rules/*.md` files for path-oriented guidance.

`CLAUDE.md` does not duplicate the full shared instructions. `AGENTS.md` remains
the shared source of truth.

Language-specific Claude rules follow the selected profile: Python rules are
included for `package` and `monorepo`, and TypeScript rules are included for
`typescript` and `monorepo`.

## Cursor

Cursor support creates `.cursor/rules/*.mdc` files plus the shared `AGENTS.md`.
Each `.mdc` file includes frontmatter with metadata such as `description`,
`alwaysApply`, and `globs` where appropriate.

Language-specific Cursor rules follow the selected profile in the same way as
Claude rules.

## Why Checks Still Matter

Instruction files guide agents, but they do not enforce behavior. Generated
projects use `scaffold-guard check`, strict local tooling, and the selected CI
provider to catch risky patterns such as type suppressions, unresolved
templates, missing adapter files, malformed Codex rules or hooks, and
mismatched configuration.

## Guidance Included

Generated agent files include practical guidance for:

- typed data modeling with dataclasses, `TypedDict`, typed mappings, and
  Pydantic only where runtime validation is justified;
- docstrings that explain behavior, invariants, side effects, and error
  handling instead of restating signatures;
- subagent delegation for bounded read-only investigation that keeps the main
  thread focused on decisions, edits, validation, and synthesis;
- optional read-only MCP usage for repository hosting, documentation, browser,
  package-index, database, or observability context when those servers are
  available.
