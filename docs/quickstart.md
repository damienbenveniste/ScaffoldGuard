# Quickstart

## Install

```bash
uv tool install scaffold-guard
scaffold-guard version
```

## Create A Project

```bash
scaffold-guard init my_project --agent all
cd my_project
uv sync --all-groups
uv run scaffold-guard check
uv run scaffold-guard validate --quick
```

Generated projects include `scaffold-guard` in the `dev` dependency group, so
`uv run scaffold-guard ...` works inside the project after
`uv sync --all-groups`.

Use one adapter when you only need one agent surface:

```bash
scaffold-guard init codex_demo --agent codex
scaffold-guard init claude_demo --agent claude
scaffold-guard init cursor_demo --agent cursor
```

## Preview Or Refresh Files

Preview a new project without writing files:

```bash
scaffold-guard init demo --dry-run
```

Refresh managed instruction files from inside a generated project:

```bash
uv run scaffold-guard compile-rules --dry-run
uv run scaffold-guard compile-rules --force
```

`compile-rules` refuses to overwrite manually edited instruction files unless
`--force` is supplied or the file has the generated marker.
