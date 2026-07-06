# Quickstart

## Install

After PyPI publication, run the CLI with `uvx`:

```bash
uvx agent-safe-python version
```

For local release testing, build the wheel and run it directly:

```bash
uv build
uvx --from dist/agent_safe_python-0.1.0-py3-none-any.whl agent-safe version
```

## Create A Project

```bash
uvx agent-safe-python init my_project --agent all
cd my_project
uv sync --all-groups
uv run agent-safe check
uv run agent-safe validate --quick
```

Use one adapter when you only need one agent surface:

```bash
uvx agent-safe-python init codex_demo --agent codex
uvx agent-safe-python init claude_demo --agent claude
uvx agent-safe-python init cursor_demo --agent cursor
```

## Preview Or Refresh Files

```bash
agent-safe init demo --dry-run
agent-safe compile-rules --path demo --dry-run
agent-safe compile-rules --path demo --force
```

`compile-rules` refuses to overwrite manually edited instruction files unless
`--force` is supplied or the file has the generated marker.
