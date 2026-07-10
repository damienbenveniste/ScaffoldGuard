#!/usr/bin/env bash
set -euo pipefail

profile="${1:?profile is required}"
wheelhouse="${2:?wheelhouse is required}"
python_version="${SMOKE_PYTHON_VERSION:-3.13}"

case "${profile}" in
  minimal | python | typescript | monorepo) ;;
  *)
    printf 'Unsupported profile: %s\n' "${profile}" >&2
    exit 2
    ;;
esac

wheel_file="$(find "${wheelhouse}" -maxdepth 1 -type f -name 'scaffold_guard-*.whl' -print -quit)"
if [[ -z "${wheel_file}" ]]; then
  printf 'No scaffold-guard wheel found in %s\n' "${wheelhouse}" >&2
  exit 2
fi

wheel_file="$(cd "$(dirname "${wheel_file}")" && pwd)/$(basename "${wheel_file}")"
wheelhouse="$(cd "${wheelhouse}" && pwd)"

uv tool install "${wheel_file}" --python "${python_version}" --force
export PATH="${HOME}/.local/bin:${PATH}"

global_version="$(scaffold-guard version)"
printf 'Global ScaffoldGuard under test: %s\n' "${global_version}"

workdir="$(mktemp -d)"
trap 'rm -rf "${workdir}"' EXIT

project_name="smoke-${profile}"
cd "${workdir}"
scaffold-guard init "${project_name}" --profile "${profile}" --agent all --ci github
cd "${workdir}/${project_name}"

export UV_FIND_LINKS="${wheelhouse}${UV_FIND_LINKS:+ ${UV_FIND_LINKS}}"

if [[ "${profile}" == "typescript" || "${profile}" == "monorepo" ]]; then
  npm install
fi

uv sync
uv pip install --python .venv/bin/python --reinstall --no-deps "${wheel_file}"

local_version="$(uv run --no-sync scaffold-guard version)"
if [[ "${local_version}" != "${global_version}" ]]; then
  printf 'Generated venv version mismatch: local=%s global=%s\n' "${local_version}" "${global_version}" >&2
  exit 1
fi

uv run --no-sync python - "${wheel_file}" <<'PY'
import json
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

expected = Path(sys.argv[1]).resolve()
site_packages = next(Path(".venv").glob("lib/python*/site-packages"))
matches = sorted(site_packages.glob("scaffold_guard-*.dist-info/direct_url.json"))
if len(matches) != 1:
    raise SystemExit(f"Expected one scaffold_guard direct_url.json, found {len(matches)}")

with matches[0].open(encoding="utf-8") as handle:
    direct_url = json.load(handle)

parsed = urlparse(direct_url.get("url", ""))
actual = Path(unquote(parsed.path)).resolve()
if actual != expected:
    raise SystemExit(f"Expected direct_url.json to resolve to {expected}, got {actual}")
PY

uv run --no-sync scaffold-guard upgrade
uv run --no-sync scaffold-guard upgrade --apply
uv run --no-sync scaffold-guard check
uv run --no-sync scaffold-guard validate --quick
uv run --no-sync scaffold-guard validate
