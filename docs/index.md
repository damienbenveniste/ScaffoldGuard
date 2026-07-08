# ScaffoldGuard

`scaffold-guard` creates strict starter repositories for coding-agent workflows.
The default `minimal` profile adds agent guardrails, GitHub Actions or GitLab
CI, local policy checks, and agent instruction files without forcing a Python
package layout. The `python`, `typescript`, and `monorepo` profiles add typed
Python, TypeScript, or mixed Python+TypeScript starter layouts.

## What V1 Provides

- `scaffold-guard init` for minimal guardrails, Python packages, TypeScript
  packages, or Python+TypeScript monorepos.
- `AGENTS.md` plus `.codex/config.toml`, `.codex/hooks.json`, and
  `.codex/rules/*.rules` when Codex is selected.
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
name to create a new project directory. Choose `python` when you want Python
source, tests, docs, and Python tooling. Choose `typescript` for npm and
TypeScript tooling. Choose `monorepo` when one repository should contain Python
and TypeScript workspaces. Python and monorepo guided setup asks for Ruff
linting strictness, Python type-checking strictness, and the Python type
checker. TypeScript and monorepo guided setup asks for TypeScript compiler,
formatter/linter, and test-runner choices. Pass `NAME` and flags for
non-interactive use with defaults. Use `--ci gitlab` when the generated project
should use GitLab CI instead of GitHub Actions.

Generated projects include CI and local development defaults, but the
user-facing CLI remains the installed `scaffold-guard` command.

Read the quickstart first, then use the adapter and checks pages when tuning a
generated project.
