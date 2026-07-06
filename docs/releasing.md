# Releasing

This page documents the manual release checklist for `agent-safe-python` itself.
Do not publish until the full gate is green and the wheel has been inspected.

## Pre-Release Gate

```bash
uv sync --all-groups --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pyright
uv run pytest tests --cov=agent_safe --cov-report=term-missing --cov-fail-under=95
uv run mkdocs build --strict
uv build
```

## Inspect The Wheel

```bash
python -m zipfile -l dist/agent_safe_python-0.1.0-py3-none-any.whl | grep templates
uvx --from dist/agent_safe_python-0.1.0-py3-none-any.whl agent-safe version
```

The wheel must include the packaged templates under `agent_safe/templates/`.

## Publish

```bash
uv publish
```

Use TestPyPI or trusted publishing only after that release path is explicitly
added and tested. Homebrew formula automation is planned after PyPI installation
is stable.
