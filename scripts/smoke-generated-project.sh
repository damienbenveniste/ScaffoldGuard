#!/usr/bin/env bash
set -euo pipefail

profile="${1:?profile is required}"
wheelhouse="${2:?wheelhouse is required}"
monorepo_layout="${3:-none}"
python_version="${SMOKE_PYTHON_VERSION:-3.13}"

case "${profile}" in
  minimal | python | typescript | monorepo) ;;
  *)
    printf 'Unsupported profile: %s\n' "${profile}" >&2
    exit 2
    ;;
esac

if [[ "${profile}" == "monorepo" && "${monorepo_layout}" == "none" ]]; then
  monorepo_layout="application"
fi

if [[ "${profile}" != "monorepo" && "${monorepo_layout}" != "none" ]]; then
  printf 'Monorepo layout requires the monorepo profile: %s\n' "${monorepo_layout}" >&2
  exit 2
fi

case "${monorepo_layout}" in
  none | application | library | custom) ;;
  *)
    printf 'Unsupported monorepo layout: %s\n' "${monorepo_layout}" >&2
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
tool_bin_dir="${UV_TOOL_BIN_DIR:-${HOME}/.local/bin}"
export PATH="${tool_bin_dir}:${PATH}"

global_version="$(scaffold-guard version)"
printf 'Global ScaffoldGuard under test: %s\n' "${global_version}"

workdir="$(mktemp -d)"
trap 'rm -rf "${workdir}"' EXIT

project_name="smoke-${profile}"
cd "${workdir}"
init_args=(
  "${project_name}"
  --profile "${profile}"
  --agent all
  --ci github
)
if [[ "${profile}" == "monorepo" ]]; then
  init_args+=(--monorepo-layout "${monorepo_layout}")
  if [[ "${monorepo_layout}" == "custom" ]]; then
    init_args+=(
      --python-workspace services/backend
      --typescript-workspace clients/browser
    )
  fi
fi
scaffold-guard init "${init_args[@]}"
cd "${workdir}/${project_name}"

if [[ "${profile}" == "monorepo" ]]; then
  case "${monorepo_layout}" in
    application)
      expected_python_workspace="apps/api"
      expected_typescript_workspace="apps/web"
      ;;
    library)
      expected_python_workspace="packages/core"
      expected_typescript_workspace="packages/client"
      ;;
    custom)
      expected_python_workspace="services/backend"
      expected_typescript_workspace="clients/browser"
      ;;
  esac
fi

export UV_FIND_LINKS="${wheelhouse}${UV_FIND_LINKS:+ ${UV_FIND_LINKS}}"

if [[ "${profile}" == "typescript" || "${profile}" == "monorepo" ]]; then
  npm install
fi

uv sync
if [[ "${profile}" == "monorepo" ]]; then
  .venv/bin/python - \
    "${monorepo_layout}" \
    "${expected_python_workspace}" \
    "${expected_typescript_workspace}" <<'PY'
import sys
import tomllib
from pathlib import Path

layout, python_workspace, typescript_workspace = sys.argv[1:]
with Path("scaffold-guard.toml").open("rb") as handle:
    config = tomllib.load(handle)

expected = {
    "layout": layout,
    "python_workspace": python_workspace,
    "typescript_workspace": typescript_workspace,
}
actual = config.get("monorepo")
if actual != expected:
    raise SystemExit(f"Expected [monorepo] config {expected}, got {actual}")
for workspace in (python_workspace, typescript_workspace):
    if not Path(workspace).is_dir():
        raise SystemExit(f"Expected generated monorepo workspace directory: {workspace}")
PY
fi
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
