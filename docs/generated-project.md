# Generated Project

The default `minimal` profile creates guardrails without package folders:

```text
my_project/
  .scaffold-guard/manifest.json
  AGENTS.md
  .codex/config.toml
  .codex/hooks.json
  .codex/agents/*.toml
  .codex/hooks/workflow-evidence.sh
  .codex/rules/git.rules
  .codex/rules/validation.rules
  README.md
  LICENSE
  pyproject.toml
  .gitignore
  scaffold-guard.toml
  .github/workflows/ci.yml  # or .gitlab-ci.yml
```

The `python` profile creates a typed Python package with docs, examples,
tests, CI, and agent instructions. Strict Ruff plus mypy and Pyright are enabled
by default. Python guided setup can switch Ruff linting and Python type checking
to `standard` or `off`, and type checking can use mypy, Pyright, or both.

```text
my_project/
  .scaffold-guard/manifest.json
  AGENTS.md
  README.md
  LICENSE
  pyproject.toml
  mkdocs.yml
  pyrightconfig.json  # when Pyright is enabled
  scaffold-guard.toml
  .github/workflows/ci.yml  # or .gitlab-ci.yml
  .github/workflows/docs.yml  # when GitHub Actions is selected
  docs/index.md
  examples/hello.py
  src/my_project/__init__.py
  src/my_project/core.py
  src/my_project/py.typed
  tests/unit/test_core.py
  tests/integration/test_import_package.py
```

All generated projects include `AGENTS.md`. Depending on `--agent`, the scaffold
also includes:

```text
# codex
.codex/config.toml
.codex/hooks.json
.codex/agents/*.toml
.codex/hooks/workflow-evidence.sh
.codex/rules/git.rules
.codex/rules/validation.rules

# claude
CLAUDE.md
.claude/rules/*.md

# cursor
.cursor/rules/*.mdc
```

The Codex files are layered: `AGENTS.md` remains behavioral guidance,
`.codex/config.toml` enables Codex features and project-scoped agent defaults,
`.codex/agents/*.toml` defines project-scoped worker defaults,
`.codex/rules/*.rules` handles command permission policy, and
`.codex/hooks.json` runs generated hook commands for mechanical workflow
evidence and checks around tool use through `.codex/hooks/workflow-evidence.sh`.
Generated Codex git rules allow repo-local
`uv run scaffold-guard publish` for intentional approval-free commits and
pushes. Raw `git commit` and `git push` are protected so publishing does not
depend on approval prompts that may be unavailable.

The `typescript` profile creates a TypeScript package with npm scripts,
TypeScript, configurable compiler strictness, optional Biome, optional Vitest,
CI, and language-aware agent instructions:

```text
my_project/
  .scaffold-guard/manifest.json
  AGENTS.md
  README.md
  LICENSE
  pyproject.toml
  package.json
  tsconfig.json
  tsconfig.build.json
  biome.json  # when Biome is enabled
  vitest.config.ts  # when Vitest is enabled
  scaffold-guard.toml
  .github/workflows/ci.yml  # or .gitlab-ci.yml
  src/index.ts
  tests/index.test.ts  # when Vitest is enabled
```

The `monorepo` profile creates one repository with Python and TypeScript
workspaces:

```text
my_project/
  .scaffold-guard/manifest.json
  AGENTS.md
  README.md
  LICENSE
  pyproject.toml
  package.json
  biome.json  # when Biome is enabled
  pyrightconfig.json  # when Pyright is enabled
  scaffold-guard.toml
  .github/workflows/ci.yml  # or .gitlab-ci.yml
  packages/python/src/my_project/
  packages/python/tests/
  packages/python/examples/
  packages/typescript/src/
  packages/typescript/tests/  # when Vitest is enabled
```

## Configuration

`scaffold-guard.toml` stores the fields V1 commands need:

- project name and import package;
- selected agent adapters;
- enabled Python and TypeScript tools;
- docs and CI provider feature flags;
- Python and test coverage settings;
- fixed quick and full validation command descriptions;
- reserved `[scaffold_guard]` metadata containing exactly `format_version`,
  `generated_with`, and `requires_scaffold_guard`.

`.scaffold-guard/manifest.json` records generated-project ownership metadata.
It contains project metadata plus managed-file records only. Project metadata
includes `manifest_version`, `project_format_version`, `generated_with`,
`requires_scaffold_guard`, `profile`, and `adapters`. Each `files` record has
exactly `path`, a stable `template_id`, and `sha256` for the exact file bytes.
Structured and seed files are not recorded, and managed-file records do not
contain a lifecycle field.

Generated files use three ownership lifecycles:

| Lifecycle | Meaning |
|---|---|
| `managed` | ScaffoldGuard may reconcile the file only when the manifest hash proves it still matches the generated baseline |
| `structured` | Migration is limited to reserved metadata in `scaffold-guard.toml` and the `scaffold-guard` development requirement or tool-carrier in `pyproject.toml` |
| `seed` | The file becomes user-owned immediately after generation and is never touched by upgrades |

V1 intentionally does not implement a general rules DSL. The generated config is
small and purpose-built for the starter repository.

## Upgrades

Use `scaffold-guard upgrade` from the generated project root to preview upgrade
work. Preview is the default and does not write files:

```bash
scaffold-guard upgrade
```

Apply only after reviewing the preview and explicitly choosing to write:

```bash
scaffold-guard upgrade --apply
scaffold-guard check
scaffold-guard validate
```

The public action kinds are exactly `unchanged`, `add`, `update`, `migrate`,
`conflict`, and `orphan`, in that order. Use `--json` for automation. `applied`
is a top-level result boolean rather than an action or status. Exit code `0`
means preview or apply completed, exit code `1` means conflicts prevent apply,
and exit code `2` covers invalid configuration, unsupported versions, failed
migrations, filesystem failures, and rollback failures.

For `0.1.x` projects that do not yet have a manifest, ScaffoldGuard uses a
strict packaged legacy baseline. Legacy managed files must match the known
generated bytes exactly to be adopted without flags. Use repeated
`--accept-legacy PATH` options only for reviewed, recognized, marker-bearing
managed files that differ. Unmarked CI or config files require manual
resolution; a generated marker alone never establishes ownership.

Legacy `0.1.x` TypeScript and monorepo projects may still have
`.scaffold-guard/` in their user-owned seed `.gitignore`; upgrade does not edit
that file. After apply, review and remove the old ignore entry, or explicitly
run `git add -f .scaffold-guard/manifest.json`, so the manifest is tracked.
Legacy TypeScript-only projects generated before the Python tool-carrier may
also need `.venv/` added manually before running `uv sync`, because `.gitignore`
is seed-owned and upgrade does not rewrite it.

Upgrades report orphans without deleting or pruning them. Review those files
manually after the upgrade, then run `scaffold-guard check` and
`scaffold-guard validate` before publishing follow-up edits.

Agent operating guidance in generated Codex, Claude Code, and Cursor files uses
repo-local commands when the generated project's pinned ScaffoldGuard version
matters:

```bash
uv run scaffold-guard upgrade
uv run scaffold-guard upgrade --apply
```

Generated Codex policy allows this repo-local command path for both preview and
the audited `--apply` form. That technical permission does not authorize a
write: behavioral guidance still requires explicit user intent and review of
the preview before an agent runs `--apply`.

## Validation

Minimal projects are expected to run:

```bash
scaffold-guard check
scaffold-guard validate --quick
```

Python-profile projects additionally use their generated Python toolchain.
Validation commands only include Ruff, mypy, and Pyright when those tools are
enabled:

```bash
uv sync --all-groups
scaffold-guard check
scaffold-guard validate --quick
scaffold-guard validate
```

TypeScript projects use npm scripts for TypeScript and whichever optional
TypeScript tools are enabled:

```bash
npm install
scaffold-guard check
scaffold-guard validate --quick
scaffold-guard validate
```

Monorepo projects use both Python and TypeScript toolchains:

```bash
uv sync --all-groups
npm install
scaffold-guard check
scaffold-guard validate --quick
scaffold-guard validate
```

Use `inspect-diff` inside a git repository to understand which checks are
required for a specific change.

## Publishing

When the user explicitly approves publishing from a generated project, use the
audited repo-local wrapper instead of raw git commit and push commands:

```bash
uv run scaffold-guard publish --message "Update project" --all
```

The repo-local invocation uses the ScaffoldGuard version pinned by the generated
project, avoiding stale global installs during approval-free publishing. Use
repeated `--file PATH` options for an exact dirty-file scope, or `--push-only`
only when the working tree is clean and existing commits need to be pushed. The
command runs generated validation first, refuses mixed staged and unstaged
scope, then commits and pushes the reviewed scope.
