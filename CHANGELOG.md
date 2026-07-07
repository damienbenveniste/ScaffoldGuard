# Changelog

## 0.1.0 - Unreleased

- Added the `scaffold-guard` CLI with `init`, `check`, `inspect-diff`, `validate`,
  `compile-rules`, `doctor`, and `version`.
- Added minimal and package profile project generation with Codex, Claude Code,
  and Cursor adapter files.
- Added local policy checks, diff guidance, generated-project validation,
  diagnostics, and rule regeneration.
- Added release-readiness documentation and wheel template inclusion checks.
- Added Python 3.14 CI coverage and PyPI Trusted Publishing release automation.
- Updated repository and generated-project GitHub Actions to current action
  releases.
- Renamed the project, PyPI distribution, module, CLI, and generated config to
  ScaffoldGuard / `scaffold-guard`.
- Added guided `scaffold-guard init` setup for first-time users.
- Added current-directory initialization from guided `scaffold-guard init` by
  leaving the project-name prompt blank.
- Made the guardrails-only `minimal` profile the default so users do not need to
  delete package folders they did not ask for.
