# Agent Instructions

These rules apply to every code, test, documentation, template, and
configuration change in this repository.

## Product Orientation

- Build `scaffold-guard`: a PyPI-installable Python CLI that generates strict
  starter repositories designed for safe coding-agent collaboration.
- Public user-facing docs should present `uv tool install scaffold-guard`
  followed by the installed `scaffold-guard` command. Do not advertise transient
  no-install execution paths, `uvx`, or `uv run scaffold-guard ...` in
  user-facing install or quickstart flows. Keep `uv run scaffold-guard ...` only
  for repo-local development, CI, or generated agent operating instructions when
  project-local dependency resolution is required.
- Preserve the V1 promise: generate a repository with clear agent instructions,
  strict local tooling, GitHub Actions CI, and policy checks that catch common
  agent mistakes. The default `minimal` profile should add guardrails only;
  `package` should be explicit when users want Python package folders and
  tooling.
- Keep `scaffold-guard init` friendly for first-time users: omitting `NAME`
  starts guided setup, and leaving the project-name prompt blank initializes
  the current empty directory. Passing `NAME` and flags remains the stable
  automation path. Keep `.` as a compatibility alias for current-directory
  automation, but do not present it as the primary guided user flow. Do not add
  guided-only generation behavior without matching non-interactive flags.
- Treat `scaffold_guard_v1_implementation_plan.md` as the source of current
  product scope and acceptance criteria until the plan is moved into formal docs.
- Keep V1 focused on a developer CLI. Do not add a SaaS dashboard, telemetry,
  external AI calls, complex YAML DSL, plugin ecosystem, publish automation, or
  automatic mutation of mature existing repositories.
- Always generate `AGENTS.md` for scaffolded projects. Treat it as the shared
  cross-agent instruction source.
- Keep adapter behavior explicit:
  - Codex uses `AGENTS.md`.
  - Claude Code uses `CLAUDE.md` as a wrapper that imports `AGENTS.md`, with
    optional `.claude/rules/`.
  - Cursor uses `.cursor/rules/*.mdc` plus `AGENTS.md`.
- Prefer small, shippable V1 behavior over speculative framework design.

## Continuous Instruction Feedback Loop

- Treat this `AGENTS.md` as the operating manual for agents working in this
  repository.
- When the user gives durable repo-wide feedback about how agents should work,
  update this file in the same task unless the feedback is clearly one-off or is
  already covered.
- Keep this file focused on operating rules, ownership boundaries, and completion
  standards. Do not use it as a roadmap, milestone tracker, or implementation
  plan.
- Keep rules general and actionable. Do not add task-specific history,
  timestamps, workaround diaries, or feature requirements.
- Final responses for implementation tasks must state whether `AGENTS.md` was
  updated. If explicit feedback or a notable failure did not require an update,
  explain why the existing rules were sufficient.

## Working Style and Completion Bar

- Start non-trivial tasks by checking the current plan, existing files, package
  boundaries, tests, and repository state.
- State assumptions, constraints, intended scope, and validation steps before
  substantial implementation.
- Make the smallest safe change that fully satisfies the request. Avoid
  speculative rewrites and unrelated refactors.
- Implement work in phases that can be validated independently. Do not treat the
  entire V1 plan as one undifferentiated change.
- Finish the accepted scope. Do not silently skip requested details or stop after
  a partial implementation.
- Never claim completion until the relevant checks have run, or until a blocker
  is stated with concrete evidence and the next action.
- If a bug is found in touched behavior, fix the root cause before calling the
  task complete unless the fix is unsafe or clearly out of scope.
- Do not lower lint, typing, docs, test, or coverage gates to force a green
  result.

## Python Tooling

- Use `uv` for dependency management, lockfile updates, virtual environment work,
  and command execution.
- The CLI package should support Python `>=3.11`.
- Test the CLI package on every supported Python feature release in CI. Do not
  leave a current supported Python release out of the matrix without an explicit
  compatibility reason.
- Generated projects should target Python `>=3.13` unless the implementation
  plan changes.
- Keep CLI runtime dependencies minimal. V1 should use `typer`, `rich`,
  `jinja2`, and `packaging` only when they are genuinely needed.
- Prefer Hatchling for package builds and make sure generated templates are
  included in wheels.
- Use `importlib.resources.files()` to load packaged templates.
- Use `subprocess.run` without `shell=True` for command execution.
- Keep enabled Ruff, mypy, Pyright, pytest, coverage, and MkDocs gates strict
  once the scaffold exists.
- Do not assume generated package projects always use Ruff, mypy, or Pyright.
  When these tools are configurable, generated dependencies, config files, CI,
  validation commands, checks, docs, and agent instructions must all honor the
  selected tool set.
- Write clear docstrings for public modules, classes, functions, and methods
  when the behavior is not obvious from the name and types.

## Types and Data Modeling

- Type every public function, method, class attribute, constant, and public
  module export.
- Avoid `Any`. If it is truly unavoidable, isolate it at a boundary, explain why,
  and add tests around the narrowing.
- Do not introduce `dict[str, Any]`. Use explicit typed structures for stable
  shapes.
- Avoid `# type: ignore`, `# pyright: ignore`, `# noqa`, broad exclusions, and
  lint suppressions to hide failures. Fix the type flow or rule violation.
- Use lightweight dataclasses or typed structures for CLI internals in V1. Do not
  add Pydantic unless the benefit clearly outweighs the dependency cost.
- Keep filesystem and rendering models explicit enough to test dry-run,
  overwrite, generated-marker, and adapter behavior deterministically.

## Scaffold and Adapter Rules

- Keep `AGENTS.md` generation in the base scaffold because it is shared by every
  adapter.
- `CLAUDE.md` must not duplicate the full `AGENTS.md`; it should import or
  reference it and add only Claude-specific notes.
- Cursor `.mdc` files must include valid frontmatter with `description`,
  `alwaysApply`, and `globs` where appropriate.
- Generated agent instruction files should be concise, serious, and enforceable
  through `scaffold-guard check` and CI where possible.
- Use generated markers and checksums or clearly documented overwrite rules for
  files managed by `compile-rules`.
- Keep template rendering deterministic. Tests should not depend on wall-clock
  time, network access, local credentials, or machine-specific paths.

## Filesystem Safety

- Validate project names before writing. Reject path traversal, empty names,
  unsafe package identifiers, and unexpected absolute paths.
- Refuse to overwrite existing directories or manually edited generated files
  unless `--force` or a documented generated-file mechanism applies.
- Write only inside the requested target project root.
- Implement `--dry-run` paths so they produce the same planned file list without
  touching the filesystem.
- Prefer structured path handling with `pathlib` over ad hoc string operations.

## Testing Rules

- Add or update tests with every behavior change.
- Unit tests should cover CLI argument handling, rendering, scaffold planning,
  filesystem safety, adapter selection, unsafe-pattern checks, diff
  requirements, generated-file checks, and config consistency.
- Integration tests should cover generated minimal and package profiles, adapter
  file sets, `compile-rules` idempotence, `validate --quick`, JSON modes, and
  import smoke behavior.
- Tests must verify behavior and regressions, not duplicate implementation
  details or mocked call order.
- Name test files after the behavior or module under test. Do not use milestone,
  roadmap, or implementation-history names.
- For bug fixes, add a regression test that fails before the fix and passes
  after it.
- Keep tests deterministic: no real network calls, sleeps, wall-clock coupling,
  or undeclared external services.
- Maintain the V1 package coverage floor at or above `95` unless the user
  explicitly approves a change.

## Documentation and Examples

- Keep `README.md`, docs, examples, generated templates, tests, and package
  behavior synchronized in the same change.
- Documentation is published to GitHub Pages with the `Deploy Docs` workflow.
  Keep `mkdocs.yml`, the README documentation link, and package metadata
  synchronized with `https://damienbenveniste.github.io/ScaffoldGuard/`.
- Update docs when public commands, package layout, configuration, validation
  behavior, generated output, adapter support, or developer workflows change.
- Never document aspirational behavior as if it works today. Future behavior
  must be marked as future, planned, or unsupported.
- Examples should be small, deterministic, realistic, and runnable enough to
  become integration fixtures later.
- Document Codex, Claude Code, and Cursor behavior as adapter facts, not vague
  compatibility claims.

## Security and Secret Handling

- Never commit secrets, local credentials, provider payloads, private
  transcripts, `.env`, `.venv`, or generated runtime artifacts.
- Keep policy checks conservative and explainable. Regex-based scanning is fine
  for V1 when it is documented and tested.
- Do not add external AI calls, telemetry, or network-dependent tests in V1.
- Treat suspicious credential literals, `shell=True`, unsafe writes outside the
  project root, and committed environment files as policy failures.

## Validation Commands

Match validation to the actual change and the scaffold that exists.

- For markdown-only edits, run `git diff --check` when the repository is
  initialized. If there is no `.git` directory yet, state that the whitespace
  check could not be run for that reason.
- For documentation pages, README changes, or docs navigation changes, run
  `git diff --check` and `uv run mkdocs build --strict` once the docs toolchain
  exists.
- For code, package metadata, lockfile, tests, examples, templates, or generated
  assets, run focused checks plus the full gate below when the change is
  substantial.

Target full gate once the scaffold exists:

```bash
uv sync --all-groups
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pyright
uv run pytest tests --cov=scaffold_guard --cov-report=term-missing --cov-fail-under=95
uv run mkdocs build --strict
```

Generated projects should be validated with their configured commands:

```bash
uv run scaffold-guard check
uv run scaffold-guard inspect-diff
uv run scaffold-guard validate
```

Do not report completion if a required check fails. Fix the failure or clearly
explain why it is blocked.

## Git and Change Hygiene

- Keep diffs focused and reviewable.
- Preserve user changes. Do not revert unrelated work.
- Keep `uv.lock` synchronized with `pyproject.toml` changes once the lockfile
  exists.
- Do not commit generated runtime artifacts unless the repository intentionally
  tracks them.
- Treat this checkout as the workspace boundary unless the user explicitly asks
  to touch another checkout.
- Treat ScaffoldGuard as an open source repository: keep `main` protected, use
  pull requests for future repository changes, keep contribution guidance
  current, and do not weaken branch protection or maintainer-only merge controls
  unless the user explicitly asks.
- When a task explicitly includes pushing or publishing, watch the relevant
  GitHub Actions runs after pushing and report the final status.

## Release Workflow

- Use short-lived release branches such as `release/v0.1.1`; do not create
  long-lived version branches.
- For a release, update `pyproject.toml`, `src/scaffold_guard/__init__.py`,
  `uv.lock`, `CHANGELOG.md`, and any version-specific release docs in the same
  pull request.
- Run the full pre-release gate and inspect the built wheel before opening or
  merging the release pull request.
- After the release pull request is squash-merged to `main`, create a GitHub
  Release tag such as `v0.1.1` from `main`; that release triggers the PyPI
  publish workflow.
- Codex may prepare the release branch, open the pull request, watch CI, merge
  when repository rules allow it, create the GitHub Release, and watch the
  publish workflow. The `pypi` environment approval is the human release gate:
  provide the maintainer the exact GitHub Actions link and wait for approval
  before verifying PyPI.

## Final Response Requirements

- Summarize the user-visible change and name the main files touched.
- List the validation commands run and their results. If a relevant check could
  not run, explain why.
- State whether `AGENTS.md` was updated for implementation tasks.
- Call out any remaining blocker, risk, or follow-up needed to finish the
  accepted scope.
