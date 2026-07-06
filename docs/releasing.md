# Releasing

This page documents the release checklist for `repo-guard` itself. Do not
publish until the full gate is green, the wheel has been inspected, and PyPI
Trusted Publishing is configured.

## Pre-Release Gate

```bash
uv sync --all-groups --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pyright
uv run pytest tests --cov=repo_guard --cov-report=term-missing --cov-fail-under=95
uv run mkdocs build --strict
uv build
```

## Inspect The Wheel

```bash
python -m zipfile -l dist/repo_guard-0.1.0-py3-none-any.whl | grep templates
uvx --from dist/repo_guard-0.1.0-py3-none-any.whl repo-guard version
```

The wheel must include the packaged templates under `repo_guard/templates/`.

## Configure PyPI

Before the first upload, create a PyPI pending publisher with these values:

```text
Project name: repo-guard
Owner: damienbenveniste
Repository: RepoGuard
Workflow: publish.yml
Environment: pypi
```

RepoGuard publishes with PyPI Trusted Publishing from GitHub Actions. Do not add
a PyPI API token or username/password secret for the release workflow.

## Publish

After PyPI has the pending publisher, publish a GitHub Release for the version
or manually run the `Publish` workflow from the `main` branch in GitHub Actions.
The workflow builds the distributions, reruns the package gate, and uploads the
`dist/` contents to PyPI.

Homebrew formula automation is planned after PyPI installation is stable.
