# Agent Instructions

Menagerist is a self-hostable collection management platform — a SvelteKit SPA frontend, a FastAPI backend, and a PostgreSQL database, deployed via Docker Compose. This file contains working instructions for AI coding agents.

## Docs map

| Document | Contents |
|---|---|
| [README.md](README.md) | Project overview and quickstart |
| [ROADMAP.md](ROADMAP.md) | Product direction and UX philosophy |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Dev setup, commands, and testing |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System topology and data model |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Why significant decisions were made |
| [backend/README.md](backend/README.md) | Backend architecture, patterns, conventions |
| [frontend/README.md](frontend/README.md) | Frontend stack, patterns, dev workflow |
| [frontend/DESIGN_GUIDELINES.md](frontend/DESIGN_GUIDELINES.md) | Frontend UX/UI rules |

## Repository layout

```
backend/src/app/
├── modules/            # bounded contexts: graph, media, …
│   └── <context>/
│       ├── domain/     # entities, value objects — no framework imports
│       ├── application/# use cases — no ports here, no adapter imports
│       ├── ports/      # Protocol interfaces defining what use cases need
│       └── adapters/
│           ├── api/            # FastAPI router (driving)
│           ├── cli/            # Cyclopts commands (driving)
│           └── persistence/    # SQLAlchemy + in-memory adapters (driven)
├── shared_kernel/      # Actor, error base types, UoW protocol, CQRS protocols
├── platform/           # database engine, session factory, logging config
└── entrypoints/        # FastAPI app factory, composition root

frontend/src/
├── routes/             # SvelteKit file-based routes (client-rendered — no +page.server.ts)
└── lib/
    ├── api/
    │   └── generated/  # auto-generated — never edit by hand
    └── …
```

## Commands

All tasks run via `poe` from the repo root. Do not invent commands — read `pyproject.toml`.

```sh
poe init                      # first-time setup: sync all deps + install git hooks
poe sync                      # sync all deps and regenerate API client

poe serve                     # backend + frontend dev servers together
poe serve-backend             # FastAPI at localhost:8000 (--reload)
poe serve-frontend            # SvelteKit at localhost:5173

poe test                      # all unit tests (backend + frontend)
poe test-backend              # backend unit + router tests — no infrastructure required
poe test-backend-integration  # integration tests — requires live Postgres
poe test-backend-all          # unit + integration with combined coverage
poe test-frontend             # Vitest unit tests

poe coverage                  # full test suite + enforce all coverage thresholds
poe typecheck                 # mypy + svelte-check + tsc
poe typecheck-backend
poe typecheck-frontend
poe lint                      # ruff + prettier + eslint
poe lint-backend
poe lint-frontend
poe format                    # ruff format + prettier (auto-fix formatting)
poe check                     # full pre-commit hooks + coverage gate (re-syncs deps first)

poe db-up                     # start local Postgres container
poe db-down                   # stop Postgres container
poe migrate                   # apply Alembic migrations

poe generate-frontend-client  # regenerate typed API client from OpenAPI schema
```

## Backend conventions

Read [backend/README.md](backend/README.md) in full before writing backend code. Key rules:

**Dependency direction** — `entrypoints → adapters → application → domain`. Nothing on the right imports anything on the left. Architecture tests in `backend/tests/architecture/` enforce this with `archunitpython` and always run in CI.

**Business logic location** — domain and application layers only. Routers translate HTTP into use-case calls and the result back into a response — nothing else. CLI commands follow the identical pattern: they are driving adapters for the same use cases.

**In-memory adapters** — every port ships a first-class in-memory implementation as a sibling file in `adapters/persistence/` (e.g. `in_memory_node_repository.py` alongside `node_repository.py`). Application-layer and router tests wire the in-memory adapter directly. Only tests verifying the real persistence adapter are `@pytest.mark.integration`.

**CQRS convention** — commands depend on `UnitOfWork` and call `commit()`. Queries depend on a repository directly and do not commit.

**Error handling** — domain errors subclass `shared_kernel.errors` base types. No `try/except` in routers. `register_exception_handlers()` maps base types to RFC 9457 HTTP responses globally; module-specific subclasses get the correct status for free.

**Entity conventions** — primary keys are `uuid7`. Timestamps set in domain methods via `datetime.now(UTC)`, not via DB defaults. All entity/mixin dataclasses use `kw_only=True, eq=False`.

**Coverage floors** (enforced by `poe coverage` and Codecov):

| Component | Threshold |
|---|---|
| domain | 100% |
| ports | tracked, no fixed floor |
| application | 100% |
| shared_kernel | 100% |
| adapters | 80% |
| platform | 70% |

`ports/` holds `Protocol` interfaces — the stub method bodies (`...`) never execute, so a hard 100% floor wouldn't test anything real. Codecov tracks it for visibility (`target: auto` in `codecov.yml`) without gating on it.

## Frontend conventions

Read [frontend/README.md](frontend/README.md) and [frontend/DESIGN_GUIDELINES.md](frontend/DESIGN_GUIDELINES.md) before writing frontend code.

- **Svelte 5 runes** — use `$state`, `$derived`, `$effect` throughout. No Svelte 4 stores except the two existing singleton controllers (`src/lib/theme.svelte.ts`, `src/lib/capture.svelte.ts`).
- **Generated API client** — `src/lib/api/generated/` is auto-generated by `@hey-api/openapi-ts`. Never edit those files. Import all API calls through `src/lib/api/client.ts`.
- **No SSR** — no `+page.server.ts`. Data is fetched client-side inside components.
- **Internal hrefs** — always use `resolve()` from `$app/paths`.
- **Design system** — shadcn-svelte + Tailwind CSS v4 + Lucide icons. Reuse existing patterns before creating new components.
- **UX rules** — [frontend/DESIGN_GUIDELINES.md](frontend/DESIGN_GUIDELINES.md) is binding. Graph terminology (node, edge, graph) must not appear in any user-visible text. Read it before implementing UI.

## General rules

- Do not add error handling, validation, or abstractions beyond what the task requires.
- Do not add comments unless the reason for the code is non-obvious to a future reader.
- Do not create documentation files unless asked.
- Do not commit unless asked.
- Backend: Python 3.14+. `poe typecheck-backend` (`mypy --strict`) must pass on any backend change.
- Frontend: TypeScript strict mode. `poe typecheck-frontend` must pass on any frontend change.
