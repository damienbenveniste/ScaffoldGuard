# Agent Adapters

## Codex

Codex uses a layered project adapter:

- `AGENTS.md` remains behavioral guidance. It defines shared operating rules
  and does not carry Codex feature toggles, command policy, or generated check
  wiring.
- `.codex/config.toml` enables Codex features and project-scoped agent defaults
  after the project is trusted.
- `.codex/agents/*.toml` defines narrow project-scoped worker and reviewer
  agents for delegated implementation, docs, and review slices.
- `.codex/rules/*.rules` handles command permission policy through allowed,
  prompted, and forbidden command prefixes.
- `.codex/hooks.json` runs generated hook commands for mechanical workflow
  evidence and checks around tool use.

The `codex` adapter currently generates project-scoped worker agents,
`.codex/rules/git.rules`, `.codex/rules/validation.rules`, and
`.codex/hooks/workflow-evidence.sh`. Its generated hooks run
`scaffold-guard check` after file-edit tool use, record subagent workflow
evidence, and warn when edits are observed without subagent start evidence.
Its generated git rules allow repo-local `uv run scaffold-guard publish` as the
audited approval-free publishing path and protect raw `git commit` and
`git push`.
They also allow the repo-local `uv run scaffold-guard upgrade` command prefix
for both preview and the audited `--apply` path. This technical permission does
not authorize a write: behavioral guidance still requires explicit user intent
and review of the preview before `--apply`.

## Claude Code

Claude Code reads `CLAUDE.md`, so the Claude adapter creates a small wrapper
that references `AGENTS.md` and adds Claude-specific notes. It also creates
`.claude/rules/*.md` files for path-oriented guidance.

`CLAUDE.md` does not duplicate the full shared instructions. `AGENTS.md` remains
the shared source of truth.

Language-specific Claude rules follow the selected profile: Python rules are
included for `python` and `monorepo`, and TypeScript rules are included for
`typescript` and `monorepo`.

Claude git hygiene guidance points to the same repo-local
`uv run scaffold-guard publish` path for intentional commits and pushes.
Generated operating guidance uses repo-local `uv run scaffold-guard upgrade`
when the project's pinned version matters. It requires explicit user intent and
review of the preview before `--apply`.

## Cursor

Cursor support creates `.cursor/rules/*.mdc` files plus the shared `AGENTS.md`.
Each `.mdc` file includes frontmatter with metadata such as `description`,
`alwaysApply`, and `globs` where appropriate.

Language-specific Cursor rules follow the selected profile in the same way as
Claude rules.

Cursor git hygiene guidance points to the same repo-local
`uv run scaffold-guard publish` path for intentional commits and pushes.
Generated operating guidance uses repo-local `uv run scaffold-guard upgrade`
when the project's pinned version matters, with explicit user intent and preview
review required before `--apply`.

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
