# Generated Project

The default `minimal` profile creates guardrails without package folders:

```text
my_project/
  AGENTS.md
  .codex/config.toml
  .codex/hooks.json
  .codex/rules/git.rules
  .codex/rules/validation.rules
  README.md
  LICENSE
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
.codex/rules/git.rules
.codex/rules/validation.rules

# claude
CLAUDE.md
.claude/rules/*.md

# cursor
.cursor/rules/*.mdc
```

The Codex files are layered: `AGENTS.md` defines behavior, `.codex/config.toml`
sets project mode and permissions, `.codex/rules/*.rules` defines command
policy, and `.codex/hooks.json` runs generated checks around tool use.

The `typescript` profile creates a TypeScript package with npm scripts,
TypeScript, configurable compiler strictness, optional Biome, optional Vitest,
CI, and language-aware agent instructions:

```text
my_project/
  AGENTS.md
  README.md
  LICENSE
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
- fixed quick and full validation command descriptions.

V1 intentionally does not implement a general rules DSL. The generated config is
small and purpose-built for the starter repository.

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
