# Releasing

This page documents the release checklist for `scaffold-guard` itself. Do not
publish until the full gate is green, the wheel has been inspected, and PyPI
Trusted Publishing is configured.

## Release Ownership

Releases use short-lived release branches and pull requests. Do not use
long-lived version branches.

Codex can prepare the release branch, bump versions, update the changelog, run
validation, open the pull request, watch CI, merge when allowed, create the
GitHub Release, and watch the publish workflow. The `pypi` environment approval
is the human release gate; the maintainer approves that deployment in GitHub
Actions before PyPI upload completes.

## Normal Flow

1. Create a short-lived branch from `main`:

   ```bash
   git switch main
   git pull --ff-only
   git switch -c release/vX.Y.Z
   ```

2. Bump the release version:

   ```text
   pyproject.toml
   src/scaffold_guard/__init__.py
   tests/integration/test_import_package.py
   uv.lock
   CHANGELOG.md
   ```

   Run `uv lock` after changing `pyproject.toml`.

3. Run the pre-release gate and inspect the wheel.

4. Push the branch and open a pull request into `main`:

   ```bash
   git push -u origin release/vX.Y.Z
   gh pr create --base main --title "Release vX.Y.Z"
   ```

5. Wait for CI, then squash-merge the pull request.

6. Create the GitHub Release from `main`:

   ```bash
   gh release create vX.Y.Z \
     --target main \
     --title "vX.Y.Z" \
     --notes-file CHANGELOG.md
   ```

   The release tag is the trigger for the `Publish` workflow.

7. Open the publish workflow run, approve the `pypi` environment deployment, and
   wait for the workflow to finish.

8. Verify the published package:

   ```bash
   uv tool install --force scaffold-guard
   scaffold-guard version
   ```

   Confirm the version matches the release.

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
VERSION=X.Y.Z
python -m zipfile -l "dist/scaffold_guard-${VERSION}-py3-none-any.whl" | grep templates
tmpdir=$(mktemp -d)
python -m venv "$tmpdir/venv"
"$tmpdir/venv/bin/python" -m pip install "dist/scaffold_guard-${VERSION}-py3-none-any.whl"
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

Prefer the GitHub Release path for normal versioned releases. Manual workflow
dispatch is for release recovery only.

Homebrew formula automation is planned after PyPI installation is stable.

## Documentation Deployment

Documentation is published to GitHub Pages at:

```text
https://damienbenveniste.github.io/ScaffoldGuard/
```

The `Deploy Docs` workflow builds MkDocs and deploys the generated `site/`
artifact when documentation-related files change on `main`. The repository Pages
source must remain set to GitHub Actions.
