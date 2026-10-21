# Architecture

Menagerist is a three-tier web application: a SvelteKit SPA frontend, a FastAPI backend, and a PostgreSQL database - deployed as Docker containers.

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

A single `menagerist` container runs the FastAPI process, which serves the pre-built frontend as a static SPA (`entrypoints/api/spa.py`, mounted at `/` after every API router) alongside the API itself - one process, one port, no reverse proxy in front of it. No server-side rendering, no API gateway, no service mesh.

Docker Compose (`compose.yaml`) orchestrates the stack: PostgreSQL plus the `menagerist` service. A machine-specific override (`compose.override.yml`) handles per-machine configuration and is picked up automatically. The container image uses a distroless base (`gcr.io/distroless/base-debian13:nonroot`) - non-root, minimal attack surface.

## Backend

Hexagonal architecture (ports and adapters) with DDD, organised as vertical slices by bounded context.

```
backend/src/app/
├── entrypoints/     # FastAPI app factory, composition root, CLI entrypoints
├── modules/         # one directory per bounded context
│   ├── collections/ # named lists of items (manual) and saved searches (smart) with their memberships
│   ├── examples/    # optional example packs: install, remove, shipped pack files
│   ├── graph/       # nodes, edges, node types, edge types
│   ├── identity/    # accounts, sessions, sign-in, first-run setup, identity CLI
│   ├── media/       # attachments and images
│   └── system/      # health, readiness, version (public: minimal; detail needs system:diagnostics:read)
├── shared_kernel/   # Actor, AccessScope/AccessPolicy, error base types, UoW protocol, CQRS protocols
├── platform/        # database engine, session factory, logging (one plausible implementation each)
└── alembic/         # migrations - one environment for all modules
```

**Dependency rule:** `entrypoints → adapters → application → domain`. Domain has zero framework imports. Enforced in CI by `archunitpython` tests in `backend/tests/architecture/`.

Each module follows this internal layout:

```
modules/<context>/
├── domain/          # entities, value objects, domain rules
├── application/     # use cases - depends on ports, never on adapter implementations
├── ports/           # Protocol interfaces - importable by application, adapters, and tests
└── adapters/
    ├── api/         # FastAPI router (driving adapter)
    ├── cli/         # Cyclopts commands (driving adapter, where needed)
    └── persistence/ # SQLAlchemy adapters + in-memory siblings (driven adapters)
```

See [backend/README.md](../backend/README.md) for the full description of every pattern.

## Access model

Every item, connection, collection, file and example installation belongs to the account that created it, and nobody else can see it (Stage 1; sharing is Stage 2).

- **`AccessScope`** (`shared_kernel/access_scope.py`) is a query criterion and carries no rules: `AccessScope.of(user_id)` (owned by that account) or `AccessScope.everyone()`. Every repository method that returns or counts content takes one as a required keyword-only `scope`, so lists, searches, counts, paging and ETags are filtered in SQL. The SQL predicate is the shared `owned_by()` in `platform/orm_mixins.py`; the in-memory twins use `AccessScope.covers()`.
- **`AccessPolicy`** (`shared_kernel/access_policy.py`) is the port that decides: `scope_for(actor)`, `assert_can_view/modify/delete(actor, owner_id)` (raising `NotFoundError`, so a foreign id looks like a missing one) and `require_admin(actor)`. `OwnerAccessPolicy` (`entrypoints/api/shared/access_policy.py`) is the only implementation: own content only, admins included. Stage 2 swaps in a sharing policy.
- **Handler bases** (`shared_kernel/cqrs.py`): `ScopedCommandHandler` / `ScopedQueryHandler` receive the policy and fetch through `policy.scope_for(actor)`; `AuthorisedCommandHandler` / `AuthorisedQueryHandler` / `AuthorisedUseCase` check a `required_permission` before `_handle` runs (used for the admin-only structure operations).
- **Ownership on entities:** domain entities compose the `Owned` mixin (`owner_id`, `shared_kernel/mixins.py`) and their models `OwnedMixin` (`platform/orm_mixins.py`). The column is nullable in the database in Stage 1, and a row with no owner is visible to nobody.
- **Permissions** are `<module>:<resource>:<action>` strings declared as an enum per module (`GraphPermission`). `RoleAuthorizationAdapter` expands an actor's grants through the `IMPLIES` catalogue; admins hold all of them. `GET /api/v1/auth/me/permissions` returns the effective set for the frontend's `can()`.

Architecture tests (`backend/tests/architecture/test_access_scope_rules.py`) require `scope` on the content ports and their implementations and a Scoped or Authorised base on every use case; `tests/entrypoints/test_cross_user_isolation.py` generates a request per route as a second account and expects 404, 403 or an empty answer.

### Request flow

```
Browser ── session cookie (HttpOnly, SameSite=Strict, `__Host-Http-` prefix when Secure); Sec-Fetch-Site / Origin on unsafe methods
  │
  ▼
verify_csrf  →  get_current_actor  →  router  →  use case  →  repository(scope)
                 │                                │
                 │ session token hash → GetCurrentUser → Actor(id, role)
                 └ 401 setup_required | 401 unauthenticated | 403 password_expired
```

`get_current_actor` (`entrypoints/api/shared/dependencies.py`) reads the session cookie, resolves it through the identity module and returns the `Actor`; the router passes it to the use case, which asks the `AccessPolicy` for the scope. Identity routes (`/api/v1/auth/*`, `/api/v1/user*`) use identity's own actor dependency so a user whose password has expired can still reach them. `/auth/status`, `/auth/setup` and `/auth/login` are public and exempt from the same-origin check (they have their own `refuse_cross_site` guard), as are health, version, docs and the SPA shell. The `identity` module imports no other module, and no content module imports it; the architecture tests enforce both.

## Frontend

Static SPA built with SvelteKit (static adapter), served by the backend process itself.

```
frontend/src/
├── routes/      # file-based SvelteKit routing - client-rendered, no +page.server.ts
└── lib/
    ├── api/
    │   ├── generated/  # auto-generated from OpenAPI schema - never edit by hand
    │   └── client.ts   # import all API calls through here
    ├── components/     # shared UI components
    └── …
```

The typed API client is generated from the backend's OpenAPI schema by `@hey-api/openapi-ts`. Regenerate it after any backend schema change with `poe generate-frontend-client`.

See [frontend/README.md](../frontend/README.md) for dev workflow and [frontend/DESIGN_GUIDELINES.md](../frontend/DESIGN_GUIDELINES.md) for UX rules.

## Data model

All data lives in PostgreSQL under a single schema. The core graph:

- **Nodes** - records of any type (items, people, events, places)
- **Node types** - named categories with optional attribute schemas
- **Edges** - typed, directed or symmetric relationships between nodes
- **Edge types** - named relationship categories with forward/reverse labels and optional attribute schemas

Identity adds two tables, `users` (username, hash, role, `password_expired`, `disabled`, sign-in throttling state) and `sessions` (token hash, expiry, last seen). Owner columns are added to `nodes`, `edges`, `media_assets` and `example_installations` (nullable; collections already had `owner_id`, NOT NULL). Collection slugs are unique per `(owner_id, slug)` and, like ids, address a collection in every `/collection/{id_or_slug}` route; a collection has a `kind` (`manual`, or `dynamic` for a smart collection) and a nullable JSONB `definition` holding a smart collection's saved search, which the `collections` module never interprets (graph evaluates it, reached through the bridges in `entrypoints/api/shared/bridges/`), and the active-pack uniqueness of example installations is per `(pack_id, owner_id)`.

**First run.** With no users, `POST /api/v1/auth/setup` creates the first administrator and, in the same transaction, assigns them every row that has no owner or a legacy owner (the fixed pre-accounts users `UUID(int=0)` and `UUID(int=1)`). The claim is a bridge in `entrypoints/api/shared/bridges/claim_existing_data.py` that calls one claim use case per module on a shared session. Setup is serialised by an advisory lock. `menagerist identity create-admin` does the same from the command line.

Every entity uses a `uuid7` primary key (time-ordered; supports keyset pagination without a separate sort column). Timestamps are set in domain methods, not by database defaults. Records are soft-deleted via a `deleted_at` timestamp.

Cross-module references use IDs, not joins across bounded-context boundaries. Bounded contexts accept eventual consistency rather than distributed transactions.

## Key decisions

See [DECISIONS.md](DECISIONS.md) for rationale behind significant architectural choices.
