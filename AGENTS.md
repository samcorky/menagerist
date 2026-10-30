# Agent Instructions

Menagerist is a self-hostable collection management platform: a SvelteKit SPA, FastAPI backend and PostgreSQL database, deployed with Docker Compose. This is the shared source of truth for coding agents; `CLAUDE.md` imports it and adds only Claude-specific tooling instructions.

## Read what the task needs

| Task                       | Guidance                                                                                                              |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Setup, commands or testing | [CONTRIBUTING.md](CONTRIBUTING.md); task definitions in `pyproject.toml`                                              |
| Backend code               | Read [backend/README.md](backend/README.md) before editing                                                            |
| Frontend code              | Read Stack, Key patterns and the relevant testing/feature sections of [frontend/README.md](frontend/README.md)        |
| UI behaviour or appearance | Read §§1–3 and §24 of [DESIGN_GUIDELINES.md](frontend/DESIGN_GUIDELINES.md), then follow its task-based reading guide |
| System/data-model changes  | [ARCHITECTURE.md](docs/ARCHITECTURE.md) and relevant [DECISIONS.md](docs/DECISIONS.md) entries                        |
| Product direction          | [ROADMAP.md](ROADMAP.md); overview and quickstart in [README.md](README.md)                                           |
| Cross-stack data/contracts | [shared/README.md](shared/README.md)                                                                                  |
| Dependency changes         | `.github/renovate.json` and the dependency policy below                                                               |

Load relevant sections, not every linked document. Keep rules in their owning document; link rather than duplicate. Document facts verified against the code, not temporary task notes.

## Commands and verification

Run tasks with `poe` from the repository root; consult `pyproject.toml` rather than inventing commands. Common entry points:

| Purpose                                       | Task                                                                                       |
| --------------------------------------------- | ------------------------------------------------------------------------------------------ |
| First-time setup / dependency sync            | `poe init` / `poe sync`                                                                    |
| Both dev servers / one server                 | `poe serve` / `poe serve-backend` / `poe serve-frontend`                                   |
| Backend unit/router tests (no infrastructure) | `poe test-backend`                                                                         |
| Backend fast tests (about 20 seconds)         | `poe test-backend-fast`                                                                    |
| Backend integration tests (live Postgres)     | `poe test-backend-integration`                                                             |
| Frontend unit tests                           | `poe test-frontend`                                                                        |
| Lint / typecheck                              | `poe lint-backend`, `poe lint-frontend`, `poe typecheck-backend`, `poe typecheck-frontend` |
| Backend coverage gate                         | `poe coverage`                                                                             |
| Checks for changed files                      | `poe check-changed`                                                                        |
| Database start / stop / migrations            | `poe db-up` / `poe db-down` / `poe migrate`                                                |
| Regenerate API client                         | `poe generate-frontend-client`                                                             |

- For test, lint, typecheck and `check-changed` tasks, use `--mode agent`. This preserves the tool's exit code and prints a compact summary; read full logs in `.agent-logs/<run>/` instead of rerunning for output (newest 20 runs retained).
- `human` runs directly without capture; `verbose` captures and streams output. Default precedence is flag, `MENAGERIST_OUTPUT`, `~/.config/menagerist/output`, then `human`.
- Use targeted tests during iteration. For backend work, `poe test-backend-fast` (about 20 seconds: domain, application, shared kernel, architecture and platform tests, the `fast` marker) is the cheap check between targeted runs; the router, adapter and integration tests are the slow bulk, so run those when you touch that code and rely on `poe coverage` for the full run. Before completion, run relevant lint, typecheck and tests for the touched code; do not run backend checks for frontend-only work or code checks for prose-only edits. Check documentation links and formatting for documentation changes.
- Backend changes must pass strict mypy (`poe typecheck-backend`) and the full `poe coverage` gate before completion; this is intentionally heavier than the iteration loop. Frontend changes must pass strict TypeScript/Svelte checking (`poe typecheck-frontend`).
- `poe check` is a broad final gate (pre-commit hooks plus coverage, resyncing dependencies), not a default iteration command. Other tasks, including end-to-end tests and formatting, are documented in CONTRIBUTING and `pyproject.toml`.
- Do not start duplicate suites against shared resources. Inspect existing logs/processes before retrying stalled or failed checks, and report blockers rather than claiming success.

## Backend conventions

Read [backend/README.md](backend/README.md) in full before writing backend code. Key rules:

**Dependency direction** - `entrypoints → adapters → application → domain`. Nothing on the right imports anything on the left. Architecture tests in `backend/tests/architecture/` enforce this with `archunitpython` and always run in CI.

**Business logic location** - domain and application layers only. Routers translate HTTP into use-case calls and the result back into a response - nothing else. CLI commands follow the identical pattern: they are driving adapters for the same use cases.

**In-memory adapters** - every port ships a first-class in-memory implementation as a sibling file in `adapters/persistence/` (e.g. `in_memory_node_repository.py` alongside `node_repository.py`). Application-layer and router tests wire the in-memory adapter directly. Only tests verifying the real persistence adapter are `@pytest.mark.integration`.

**CQRS convention** - commands depend on `UnitOfWork` and call `commit()`. Queries depend on a repository directly and do not commit.

**Access stances** - every use case sets `access = ...` (`Public`, `System`, `OwnAccount`, `Content(permission)` or `Requires(permission)`, from `shared_kernel/access.py`) and implements `_handle`, never `handle`; the final `handle` runs the `AccessGuard` check first. Content use cases fetch with `self.scope(actor)` and call `self._guard.assert_can_*`. An architecture test fails a use case without a stance, and the `Public`, `System`, `OwnAccount` and `Content` sets are pinned by name in `tests/architecture/test_access_stances.py`, so widening access means editing the pin. Token actors carry `Actor.grants`; `OwnAccount` refuses them and `Content`/`Requires` check the owner's permissions intersected with the grants.

**Error handling** - domain errors subclass `shared_kernel.errors` base types. No `try/except` in routers. `register_exception_handlers()` maps base types to RFC 9457 HTTP responses globally; module-specific subclasses get the correct status for free.

**Entity conventions** - primary keys are `uuid7`. Timestamps set in domain methods via `datetime.now(UTC)`, not via DB defaults. All entity/mixin dataclasses use `kw_only=True, eq=False`.

**Coverage floors** (enforced by `poe coverage` and Codecov):

| Component     | Threshold               |
| ------------- | ----------------------- |
| domain        | 100%                    |
| ports         | tracked, no fixed floor |
| application   | 100%                    |
| shared_kernel | 100%                    |
| adapters      | 80%                     |
| platform      | 70%                     |

`poe coverage` is a full verification step, not a quick iteration command: it runs the full backend test suite and fails if any layer drops below the thresholds above. Use targeted backend tests while developing, then run `poe coverage` before considering backend work complete. It is intentionally heavier than `poe test-backend` and is the source of truth for the repository's coverage gate.

`ports/` holds `Protocol` interfaces - the stub method bodies (`...`) never execute, so a hard 100% floor wouldn't test anything real. Codecov tracks it for visibility (`target: auto` in `codecov.yml`) without gating on it.

## Frontend conventions

Engineering details live in [frontend/README.md](frontend/README.md); product rules live in [DESIGN_GUIDELINES.md](frontend/DESIGN_GUIDELINES.md). Keep implementation instructions in the former and UX decisions in the latter.

- Use Svelte 5 runes; existing singleton controllers and their exceptions are documented in the frontend README.
- The app is client-rendered: no `+page.server.ts`. Fetch through `src/lib/api/client.ts`; never hand-edit `src/lib/api/generated/`.
- Use `resolve()` from `$app/paths` for internal hrefs.
- Reuse the shadcn-svelte/bits-ui, Tailwind v4 and Lucide system. Fixed-choice value inputs default to `ui/native-select`; see design §15 for exceptions.
- Use collector-facing terms from design §24. Standard UI never exposes node/edge/graph terminology; the deliberately advanced Explore exception is defined in §17.

## General rules

- Use British English for copy, comments and documentation unless an API, library or established convention requires otherwise. Comments should explain otherwise-unclear intent, briefly and factually.
- Keep changes focused. Do not add error handling, validation or abstractions beyond the task. Do not create documentation files unless asked.
- Add/update dependencies only when necessary or clearly justified. Check Renovate grouping, schedules, automerge and review rules first; majors/runtime dependencies follow its manual-review policy. Prefer targeted, maintainable options and consider Docker image size, runtime footprint and overlap with existing libraries.
- Backend requires Python 3.14+; backend typing/docstring conventions are in its README.
- **Never stage, create, amend, squash or push commits, or run an auto-commit workflow on the user's behalf.** Do not run `git add` or `git commit`. If a commit is needed, let the user run it themselves.
