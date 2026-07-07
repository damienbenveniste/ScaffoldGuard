# Generated Project

The default `minimal` profile creates guardrails without package folders:

```text
my_project/
  AGENTS.md
  README.md
  LICENSE
  .gitignore
  scaffold-guard.toml
  .github/workflows/ci.yml
```

The `package` profile creates a typed Python package with docs, examples,
tests, CI, and agent instructions.

```text
my_project/
  AGENTS.md
  README.md
  LICENSE
  pyproject.toml
  pyrightconfig.json
  scaffold-guard.toml
  .github/workflows/ci.yml
  .github/workflows/docs.yml
  docs/index.md
  examples/hello.py
  src/my_project/__init__.py
  src/my_project/core.py
  src/my_project/py.typed
  tests/unit/test_core.py
  tests/integration/test_import_package.py
```

Depending on `--agent`, the scaffold also includes:

```text
CLAUDE.md
.claude/rules/*.md
.cursor/rules/*.mdc
```

## Configuration

`scaffold-guard.toml` stores the fields V1 commands need:

- project name and import package;
- selected agent adapters;
- docs and GitHub Actions feature flags;
- Python and coverage settings;
- fixed quick and full validation command descriptions.

V1 intentionally does not implement a general rules DSL. The generated config is
small and purpose-built for the starter repository.

## Validation

Minimal projects are expected to run:

```bash
scaffold-guard check
scaffold-guard validate --quick
```

Package projects additionally use their generated Python toolchain:

```bash
uv sync --all-groups
scaffold-guard check
scaffold-guard validate --quick
scaffold-guard validate
```

Use `inspect-diff` inside a git repository to understand which checks are
required for a specific change.
