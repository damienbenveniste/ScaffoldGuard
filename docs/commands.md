# Command Reference

Run commands from the generated project root unless you pass `--path`.
Generated projects contain `scaffold-guard.toml`; the ScaffoldGuard source
repository itself is not a generated project.

## Common Workflow

Use this loop while changing a generated project:

```bash
scaffold-guard check
scaffold-guard inspect-diff
scaffold-guard validate --quick
scaffold-guard validate
```

`check` is the fast policy gate. `inspect-diff` tells you which validation
evidence a change needs. `validate --quick` runs the generated quick gate.
`validate` runs the full configured gate.

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

## `compile-rules`

Regenerate managed agent instruction files from the current project
configuration and ScaffoldGuard templates.

```bash
scaffold-guard compile-rules [--path .] [--agent codex|claude|cursor|all] [--dry-run] [--force]
```

Use `compile-rules` after changing adapter selection or when you want to refresh
managed instruction files. Start with `--dry-run` to see the planned files.

By default, `compile-rules` refuses to overwrite manually edited files. Use
`--force` only when you intentionally want to replace managed generated files.

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
