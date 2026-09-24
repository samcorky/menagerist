# Architecture

Menagerist is a three-tier web application: a SvelteKit SPA frontend, a FastAPI backend, and a PostgreSQL database — deployed as Docker containers.

## Deployment topology

```
Browser
  │
  ▼
menagerist (port 8000, distroless)
  ├── /*      → SvelteKit static build (served directly)
  └── /api/*  → FastAPI (same process)
              │
              ▼
         PostgreSQL
```

A single `menagerist` container runs the FastAPI process, which serves the pre-built frontend as a static SPA (`entrypoints/api/spa.py`, mounted at `/` after every API router) alongside the API itself — one process, one port, no reverse proxy in front of it. No server-side rendering, no API gateway, no service mesh.

Docker Compose (`compose.yaml`) orchestrates the stack: PostgreSQL plus the `menagerist` service. A machine-specific override (`compose.override.yml`) handles per-machine configuration and is picked up automatically. The container image uses a distroless base (`gcr.io/distroless/base-debian13:nonroot`) — non-root, minimal attack surface.

## Backend

Hexagonal architecture (ports and adapters) with DDD, organised as vertical slices by bounded context.

```
backend/src/app/
├── entrypoints/     # FastAPI app factory, composition root, CLI entrypoints
├── modules/         # one directory per bounded context
│   ├── graph/       # nodes, edges, node types, edge types
│   ├── media/       # attachments and images
│   └── system/      # health, readiness, and version endpoints
├── shared_kernel/   # Actor, error base types, UoW protocol, CQRS protocols
├── platform/        # database engine, session factory, logging (one plausible implementation each)
└── alembic/         # migrations — one environment for all modules
```

**Dependency rule:** `entrypoints → adapters → application → domain`. Domain has zero framework imports. Enforced in CI by `archunitpython` tests in `backend/tests/architecture/`.

Each module follows this internal layout:

```
modules/<context>/
├── domain/          # entities, value objects, domain rules
├── application/     # use cases — depends on ports, never on adapter implementations
├── ports/           # Protocol interfaces — importable by application, adapters, and tests
└── adapters/
    ├── api/         # FastAPI router (driving adapter)
    ├── cli/         # Cyclopts commands (driving adapter, where needed)
    └── persistence/ # SQLAlchemy adapters + in-memory siblings (driven adapters)
```

See [backend/README.md](../backend/README.md) for the full description of every pattern.

## Frontend

Static SPA built with SvelteKit (static adapter), served by the backend process itself.

```
frontend/src/
├── routes/      # file-based SvelteKit routing — client-rendered, no +page.server.ts
└── lib/
    ├── api/
    │   ├── generated/  # auto-generated from OpenAPI schema — never edit by hand
    │   └── client.ts   # import all API calls through here
    ├── components/     # shared UI components
    └── …
```

The typed API client is generated from the backend's OpenAPI schema by `@hey-api/openapi-ts`. Regenerate it after any backend schema change with `poe generate-frontend-client`.

See [frontend/README.md](../frontend/README.md) for dev workflow and [frontend/DESIGN_GUIDELINES.md](../frontend/DESIGN_GUIDELINES.md) for UX rules.

## Data model

All data lives in PostgreSQL under a single schema. The core graph:

- **Nodes** — records of any type (items, people, events, places)
- **Node types** — named categories with optional attribute schemas
- **Edges** — typed, directed or symmetric relationships between nodes
- **Edge types** — named relationship categories with forward/reverse labels and optional attribute schemas

Every entity uses a `uuid7` primary key (time-ordered; supports keyset pagination without a separate sort column). Timestamps are set in domain methods, not by database defaults. Records are soft-deleted via a `deleted_at` timestamp.

Cross-module references use IDs, not joins across bounded-context boundaries. Bounded contexts accept eventual consistency rather than distributed transactions.

## Key decisions

See [DECISIONS.md](DECISIONS.md) for rationale behind significant architectural choices.
