# Changelog

## 0.1.5 - 2026-07-09

- Fixed `compile-rules` so generated markers alone no longer authorize an
  overwrite; differing managed content now requires explicit `--force`.

## 0.1.4 - 2026-07-08

- Fixed generated Codex publish policy templates to allow the audited
  `scaffold-guard publish` path only when the generated project depends on a
  ScaffoldGuard version that includes that command.

## 0.1.3 - 2026-07-08

- Added `scaffold-guard publish` as an audited generated-project commit and
  push path for approval-free Codex sessions.
- Updated generated Codex git rules to allow `scaffold-guard publish` while
  protecting raw `git commit` and `git push`.
- Added matching Claude Code, Cursor, and shared `AGENTS.md` guidance for the
  safe publish workflow.
- Documented the new `publish` command and added regression coverage,
  including a local bare-remote publish smoke test.

## 0.1.2 - 2026-07-08

- Allowed `scaffold-guard init` to initialize an existing directory when its
  existing files do not conflict with planned generated destinations.
- Kept generated-file overwrite protection strict: existing generated
  destinations still require `--force`, and ScaffoldGuard stops before partial
  writes.
- Added regression coverage for guided current-directory initialization with an
  unrelated existing plan file.
- Added a dedicated command reference page and linked it from public docs.
- Removed the obsolete V1 implementation plan file from the repository.

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
