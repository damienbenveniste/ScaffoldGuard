# Command Reference

Run commands from the generated project root unless you pass `--path`.
Generated projects contain `scaffold-guard.toml`; the ScaffoldGuard source
repository itself is not a generated project.

## Common Workflow

Use this loop while changing a generated project:

```bash
scaffold-guard check
scaffold-guard inspect-diff
scaffold-guard upgrade
scaffold-guard validate --quick
scaffold-guard validate
uv run scaffold-guard publish --message "Update project" --all
```

`check` is the fast policy gate. `inspect-diff` tells you which validation
evidence a change needs. `upgrade` previews generated-project maintenance
without writing files. `validate --quick` runs the generated quick gate.
`validate` runs the full configured gate. Repo-local
`uv run scaffold-guard publish` validates, commits, and pushes an explicitly
reviewed scope with the ScaffoldGuard version pinned by the generated project.

## `init`

Create a new generated project.

```bash
scaffold-guard init [NAME]
```

Omit `NAME` to start guided setup. At the project-name prompt, press Enter to
initialize the current directory or enter a name to create a new directory. Pass
`NAME` and flags for non-interactive use.

When initializing an existing directory, ScaffoldGuard preserves unrelated files.
It stops before writing if any planned generated destination already exists.
Use `--force` only when you intentionally want to overwrite generated files.

Common options:

| Option | Use |
|---|---|
| `--profile minimal|python|typescript|monorepo` | Choose guardrails only, Python, TypeScript, or mixed workspaces |
| `--agent codex|claude|cursor|all` | Choose generated agent adapter files |
| `--ci github|gitlab` | Choose GitHub Actions or GitLab CI |
| `--guided` | Prompt for options even when `NAME` is provided |
| `--dry-run` | Show the planned files without writing them |
| `--force` | Overwrite known generated files |

Python and monorepo profiles also accept Ruff and Python type-checking options.
TypeScript and monorepo profiles also accept TypeScript compiler, formatter,
linter, and test-runner options.

## `check`

Run fast local policy checks without executing the generated project's full test
suite or build.

```bash
scaffold-guard check [--path .] [--json]
```

Use `check` before commits, before opening pull requests, and after agent edits.
It catches common coding-agent mistakes such as unsafe suppressions, suspicious
secret literals, unsafe shell usage, stale generated files, malformed adapter
files, and configuration drift.

Exit codes:

| Code | Meaning |
|---|---|
| `0` | Checks passed |
| `1` | Policy findings were found |
| `2` | Configuration or tool error |

Use `--json` when CI or another tool needs stable machine-readable output.

## `inspect-diff`

Report which validation evidence is expected for the current git diff.

```bash
scaffold-guard inspect-diff [--path .] [--base main] [--json]
```

Use `inspect-diff` after making changes and before claiming work is complete. It
does not run validation commands. It classifies changed files and reports the
checks or evidence that should accompany the change.

Examples:

- docs-only changes usually need whitespace and docs-build evidence;
- source, template, or configuration changes usually need policy checks,
  formatting, type checks, tests, and generated-project validation;
- package metadata changes may require lockfile or build evidence.

Use `--base` when your comparison branch is not `main`.

## `validate`

Run the validation commands configured in `scaffold-guard.toml`.

```bash
scaffold-guard validate [--path .] [--quick] [--json]
```

Use `validate --quick` for the fast generated-project gate during local
iteration. Use `validate` before a pull request or release when you need the
full configured gate.

Unlike `check`, `validate` executes commands. Depending on the generated
profile, that can include Python, TypeScript, tests, coverage, docs, and package
build steps.

Exit codes:

| Code | Meaning |
|---|---|
| `0` | All configured commands passed |
| `1` | A configured validation command failed |
| `2` | Configuration or tool error |

## `upgrade`

Preview or apply a generated-project upgrade.

```bash
scaffold-guard upgrade [--path .] [--apply] [--json] [--accept-legacy PATH]
```

Preview is the default and is read-only. Use it first to inspect the ordered
file actions and any conflicts:

```bash
scaffold-guard upgrade
```

Pass `--apply` only after reviewing the preview and explicitly choosing to let
ScaffoldGuard write the upgrade. Any conflict prevents apply:

```bash
scaffold-guard upgrade --apply
scaffold-guard check
scaffold-guard validate
```

`upgrade` works from generated-project metadata. Current generated projects have
`.scaffold-guard/manifest.json` plus a reserved `[scaffold_guard]` table in
`scaffold-guard.toml`. The manifest contains project metadata and managed-file
records only. Its project metadata includes `manifest_version`,
`project_format_version`, `generated_with`, `requires_scaffold_guard`, `profile`,
and `adapters`. Each `files` record has exactly `path`, a stable `template_id`,
and `sha256` for the exact file bytes. The manifest does not store `structured`
or `seed` entries, and its file records have no lifecycle field.

The reserved `[scaffold_guard]` table contains exactly `format_version`,
`generated_with`, and `requires_scaffold_guard`.

File ownership is lifecycle-based:

| Lifecycle | Upgrade behavior |
|---|---|
| `managed` | Reconciled only when the recorded hash proves the current file still matches the generated baseline |
| `structured` | Limited to reserved metadata in `scaffold-guard.toml` and the `scaffold-guard` development requirement or tool-carrier in `pyproject.toml` |
| `seed` | User-owned immediately after generation and never touched by upgrade |

The public action kinds are exactly `unchanged`, `add`, `update`, `migrate`,
`conflict`, and `orphan`, in that order:

| Action | Meaning |
|---|---|
| `unchanged` | Current content already matches the desired content |
| `add` | A missing generated path or required tool-carrier can be added |
| `update` | A managed file has a clean recorded baseline and new generated content |
| `migrate` | A supported structured field change can be made |
| `conflict` | Drift, ambiguity, or an unsafe path prevents apply |
| `orphan` | A previously managed path is no longer selected and remains in place |

Use `--json` when tooling needs structured output. `applied` is a top-level
result boolean, not an action or status: it is `false` for previews and when
conflicts prevent apply, and `true` when the apply path runs.

Manifest-less `0.1.x` projects use strict legacy baseline recognition. A legacy
project whose complete managed surface exactly matches a packaged baseline is
adopted without flags. Use `--accept-legacy PATH` only for one reviewed,
recognized, marker-bearing managed file that differs from that baseline; repeat
the option for each such path. Unmarked CI or config files, unrecognized paths,
missing expected files, and ambiguous legacy content remain conflicts and
require manual resolution.

Legacy `0.1.x` TypeScript and monorepo projects may still have
`.scaffold-guard/` in their user-owned seed `.gitignore`; upgrade does not edit
that file. After apply, review and remove the old ignore entry, or explicitly
run `git add -f .scaffold-guard/manifest.json`, so the manifest is tracked.
Legacy TypeScript-only projects generated before the Python tool-carrier may
also need `.venv/` added manually before running `uv sync`, because `.gitignore`
is seed-owned and upgrade does not rewrite it.

`upgrade` does not delete or prune files. The `orphan` action reports a formerly
managed file that remains in place for manual review.

Exit codes:

| Code | Meaning |
|---|---|
| `0` | Preview completed, apply completed, or no upgrade work was needed |
| `1` | Conflicts prevent apply |
| `2` | Invalid configuration, unsupported version, failed migration, filesystem failure, or rollback failure |

## `publish`

Validate, commit, and push a generated project through an audited path that does
not rely on raw `git commit` or `git push` prompts.

```bash
uv run scaffold-guard publish --message "Update project" --all
uv run scaffold-guard publish --message "Update docs" --file README.md --file docs/index.md
uv run scaffold-guard publish --push-only
```

Use repo-local `uv run scaffold-guard publish` when an agent has explicit user
approval to publish work, especially in Codex sessions where approval prompts
are unavailable. This avoids stale global installs shadowing the generated
project's pinned ScaffoldGuard version. By default, it runs the full configured
validation gate before staging or pushing. Pass `--quick` only when the quick
gate is the accepted validation scope.

Safety behavior:

- `--message` is required unless `--push-only` is used.
- `--all` stages every dirty file after validation.
- `--file` must cover the full dirty scope; unselected dirty files stop the
  publish.
- mixed staged and unstaged work is refused.
- `--push-only` requires a clean working tree.

Common options:

| Option | Use |
|---|---|
| `--message`, `-m` | Commit message for the reviewed changes |
| `--all` | Stage and publish every dirty file |
| `--file PATH` | Publish an exact dirty-file scope; repeat for multiple files |
| `--remote NAME` | Push to a specific remote instead of upstream or `origin` |
| `--branch NAME` | Push `HEAD` to a specific remote branch |
| `--quick` | Run quick validation before publishing |
| `--push-only` | Push existing commits without creating a commit |

Exit codes:

| Code | Meaning |
|---|---|
| `0` | Validation, commit if requested, and push succeeded |
| `2` | Configuration, validation, git, or safety error |

## `compile-rules`

Regenerate managed agent instruction files from the current project
configuration and ScaffoldGuard templates.

```bash
scaffold-guard compile-rules [--path .] [--agent codex|claude|cursor|all] [--dry-run] [--force]
```

Use `compile-rules` after changing adapter selection or when you want to refresh
managed instruction files. Start with `--dry-run` to see the planned files.

By default, `compile-rules` regenerates an existing managed file only when its
current content exactly matches the content ScaffoldGuard would render. The
generated marker identifies managed files, but the marker alone is not proof
that default regeneration can replace the file. Use `--force` only after review
when you intentionally want to replace managed generated files.

`compile-rules` requires the active ScaffoldGuard version to match the
project's `generated_with` metadata. After updating ScaffoldGuard, preview and
apply `scaffold-guard upgrade` before compiling rules so structured metadata and
managed templates advance in one reviewed transaction.

## `doctor`

Report local environment and generated-project health.

```bash
scaffold-guard doctor [--path .] [--json]
```

Use `doctor` when a generated project behaves unexpectedly, when CI and local
results differ, or when a new machine is missing expected tools. It checks for
project configuration, selected adapter files, selected CI files, language
tooling, and git state.

## `version`

Print the installed ScaffoldGuard version.

```bash
scaffold-guard version
```

Use this in bug reports, release verification, and local environment checks.
