# Releasing

This page documents the release checklist for `scaffold-guard` itself. Do not
publish until the full gate is green, the wheel has been inspected, and PyPI
Trusted Publishing is configured.

## Pre-Release Gate

```bash
uv sync --all-groups --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pyright
uv run pytest tests --cov=scaffold_guard --cov-report=term-missing --cov-fail-under=95
uv run mkdocs build --strict
uv build
```

## Inspect The Wheel

```bash
python -m zipfile -l dist/scaffold_guard-0.1.0-py3-none-any.whl | grep templates
tmpdir=$(mktemp -d)
python -m venv "$tmpdir/venv"
"$tmpdir/venv/bin/python" -m pip install dist/scaffold_guard-0.1.0-py3-none-any.whl
"$tmpdir/venv/bin/scaffold-guard" version
rm -rf "$tmpdir"
```

The wheel must include the packaged templates under `scaffold_guard/templates/`.

## PyPI Configuration

ScaffoldGuard publishes with PyPI Trusted Publishing from GitHub Actions. The
publisher is configured with these values:

```text
Project name: scaffold-guard
Owner: damienbenveniste
Repository: ScaffoldGuard
Workflow: publish.yml
Environment: pypi
```

Do not add a PyPI API token or username/password secret for the release workflow.

## Publish

Create a GitHub Release for the version or manually run the `Publish` workflow
from the `main` branch in GitHub Actions. The workflow builds the distributions,
reruns the package gate, and uploads the `dist/` contents to PyPI.

Homebrew formula automation is planned after PyPI installation is stable.
