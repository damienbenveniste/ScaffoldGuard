# Quickstart

## Install

```bash
uv tool install scaffold-guard
scaffold-guard version
```

## Create A Project

Start the guided setup and answer the prompts. This example assumes you enter
`my_project` as the project name.

```bash
scaffold-guard init
cd my_project
uv sync --all-groups
scaffold-guard check
scaffold-guard validate --quick
```

Generated projects include CI and local development defaults, but the
user-facing CLI remains the installed `scaffold-guard` command.

For non-interactive use, pass the options as flags:

```bash
scaffold-guard init my_project --agent all
```

If you already created and entered an empty project folder, start guided setup
for the current directory:

```bash
scaffold-guard init .
```

For non-interactive current-directory setup, pass the options as flags:

```bash
scaffold-guard init . --agent codex
```

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
scaffold-guard compile-rules --dry-run
scaffold-guard compile-rules --force
```

`compile-rules` refuses to overwrite manually edited instruction files unless
`--force` is supplied or the file has the generated marker.
