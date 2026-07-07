# Checks

`scaffold-guard check` runs fast local checks that do not execute the full project
test suite.

```bash
scaffold-guard check [--path .] [--json]
```

Exit codes:

| Code | Meaning |
|---|---|
| `0` | all checks passed |
| `1` | policy findings were found |
| `2` | invalid configuration or tool error |

## Checkers

### unsafe-patterns

Detects common risky agent outputs, including:

- `# type: ignore` when mypy policy is enabled;
- `# pyright: ignore` when Pyright policy is enabled;
- `# noqa:` when Ruff policy is enabled;
- `Any` imports and `dict[str, Any]`;
- suspicious secret literals;
- `subprocess.run(..., shell=True)`;
- committed `.env`, `.venv`, or runtime artifact directories.

### project-health

Verifies the expected generated project structure exists, including
`pyproject.toml`, `AGENTS.md`, source, tests, docs, CI, adapter-specific files,
and `pyrightconfig.json` when Pyright is enabled.

### generated-files

Checks generated instruction and support files for unresolved template
placeholders, valid Cursor frontmatter, README `uv` commands, and CI commands
for the enabled toolchain.

### config-consistency

Compares `scaffold-guard.toml` against generated files and package configuration.
It detects agent adapter mismatches, Python version mismatches, coverage
mismatches, and stale lockfiles when a lockfile exists.

## JSON Output

Use `--json` when a script or CI job needs stable output:

```bash
scaffold-guard check --json
```
