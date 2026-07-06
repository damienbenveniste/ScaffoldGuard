# Quickstart

## Install

After PyPI publication, run the CLI with `uvx`:

```bash
uvx --from repo-guard-cli repo-guard version
```

For local release testing, build the wheel and run it directly:

```bash
uv build
uvx --from dist/repo_guard_cli-0.1.0-py3-none-any.whl repo-guard version
```

## Create A Project

```bash
uvx --from repo-guard-cli repo-guard init my_project --agent all
cd my_project
uv sync --all-groups
uv run repo-guard check
uv run repo-guard validate --quick
```

Use one adapter when you only need one agent surface:

```bash
uvx --from repo-guard-cli repo-guard init codex_demo --agent codex
uvx --from repo-guard-cli repo-guard init claude_demo --agent claude
uvx --from repo-guard-cli repo-guard init cursor_demo --agent cursor
```

## Preview Or Refresh Files

```bash
repo-guard init demo --dry-run
repo-guard compile-rules --path demo --dry-run
repo-guard compile-rules --path demo --force
```

`compile-rules` refuses to overwrite manually edited instruction files unless
`--force` is supplied or the file has the generated marker.
