# Changelog

## 0.1.1 - 2026-07-08

- Updated public docs to present the installed `scaffold-guard` command and
  hide transient no-install execution paths from user-facing quickstarts.
- Added guided `scaffold-guard init` setup, including current-directory
  initialization by leaving the project-name prompt blank.
- Made the guardrails-only `minimal` profile the default so users do not need to
  delete package folders they did not ask for.
- Added GitLab CI scaffold support.
- Added configurable Python quality-tool presets for Ruff, mypy, and Pyright.
- Added TypeScript and Python+TypeScript monorepo scaffold profiles.
- Strengthened generated agent guidance for docstrings, typed data modeling,
  subagent delegation, MCP usage, and Codex layered configuration files.
- Added repo-local `.codex/` workflow configuration for ScaffoldGuard
  development.
- Fixed Pylance unknown-type findings for module constants.
- Updated repository and generated-project GitHub Actions to current action
  releases.

## 0.1.0 - 2026-07-06

- Added the `scaffold-guard` CLI with `init`, `check`, `inspect-diff`, `validate`,
  `compile-rules`, `doctor`, and `version`.
- Added minimal and package profile project generation with Codex, Claude Code,
  and Cursor adapter files.
- Added local policy checks, diff guidance, generated-project validation,
  diagnostics, and rule regeneration.
- Added release-readiness documentation and wheel template inclusion checks.
- Added Python 3.14 CI coverage and PyPI Trusted Publishing release automation.
- Renamed the project, PyPI distribution, module, CLI, and generated config to
  ScaffoldGuard / `scaffold-guard`.
