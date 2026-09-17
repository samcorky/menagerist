# Technical Decisions

Significant architectural choices and their rationale. Entries are added when a decision is made and updated when circumstances change. For the overall system structure, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Hexagonal architecture with a strict dependency rule

**Decision:** The backend uses hexagonal (ports and adapters) architecture. The enforced dependency direction is `entrypoints → adapters → application → domain`. Domain has zero framework imports; application depends only on port Protocols it defines itself.

**Rationale:** Keeps business logic testable without running a web server or database. Domain entities and use cases can be instantiated with no infrastructure. The dependency rule is not convention — it is checked at CI time by `archunitpython` tests in `backend/tests/architecture/`.

**Tradeoff:** More boilerplate per bounded context than a flat structure. The test-speed and design-clarity benefits are judged to compound as the codebase grows.

---

## Vertical slices by bounded context, not horizontal layers

**Decision:** Code is organised as `modules/<context>/` (domain, application, ports, adapters), not as repo-wide `models/`, `services/`, `routers/` directories.

**Rationale:** Horizontal organisation couples every feature to every other feature at the import level. Vertical slices keep a module's internals self-contained — adding a bounded context does not require touching every layer. The organising question is "what domain concept is this about?", not "what kind of code is this?".

---

## UUID7 primary keys

**Decision:** Every entity primary key is a `uuid7` generated in the domain layer at construction time.

**Rationale:** UUID7 is time-ordered, so it supports keyset pagination (`after: UUID | None, limit: int`) without a separate sort column. Generated in the domain layer so IDs are consistent across persistence implementations and testable without a database.

---

## In-memory adapters as first-class citizens

**Decision:** Every port ships an in-memory implementation alongside its SQLAlchemy implementation as a sibling file in `adapters/persistence/`. Application-layer and router tests wire the in-memory adapter directly.

**Rationale:** Mock-based tests can pass while the real adapter is broken — this has happened once where mock/prod divergence masked a broken migration. In-memory adapters satisfy the same port Protocol as the real adapter, so tests exercise the actual contract. They also keep the unit test loop near-instant.

**Tradeoff:** Two implementations per port. In-memory implementations are typically trivial (an in-memory dict or list) and the test-correctness and speed benefits are worth it.

---

## Timestamps set in the domain layer

**Decision:** Entity `created_at` and `updated_at` are set in domain methods via `datetime.now(UTC)`, not via SQLAlchemy `server_default` or `onupdate`.

**Rationale:** Timestamping is domain behaviour, not a database side effect. Setting it in domain methods makes it testable with `freezegun`/`time-machine` without a live database, and ensures it behaves consistently across persistence backends.

---

## Shared `UnitOfWork` Protocol, not per-module subclasses

**Decision:** `shared_kernel/unit_of_work.py` defines `UnitOfWork[TRepos]` once. Two concrete implementations exist (`SqlAlchemySessionUnitOfWork` in `platform/`, `InMemoryUnitOfWork` in `shared_kernel/`), written once and reused by every module. A module contributes only a `Repos` dataclass and two one-line factory functions.

**Rationale:** A per-module UoW subclass repeats session lifecycle code (begin/rollback/close/commit) N times. A single central UoW listing all modules' repos was rejected — it couples modules to each other and implies transactions spanning bounded contexts, which DDD treats as the wrong boundary.

---

## CQRS as a typing convention, not a bus

**Decision:** `shared_kernel/cqrs.py` defines `CommandHandler[TCommand, TResult]` and `QueryHandler[TQuery, TResult]` Protocols. Every use case implements one. Routers call use cases directly — there is no mediator, dispatcher, or pipeline.

**Rationale:** The pattern enforces a consistent shape for every use case and makes `mypy --strict` verify it. A bus with pipeline behaviors would give a single seam for cross-cutting concerns, but nothing currently requires that uniformity enforced. Adding a bus later is possible — the typed-handler convention is a prerequisite and is already in place.

---

## Static SPA, not server-side rendering

**Decision:** The SvelteKit frontend uses the static adapter. No `+page.server.ts`. Data is fetched client-side inside components.

**Rationale:** Menagerist is a self-hosted personal app, not a public-facing site requiring SEO or SSR performance. A static build simplifies deployment (nginx serves a directory), eliminates a Node.js runtime from the production image, and makes the Docker setup self-contained. First-load skeleton states are an acceptable tradeoff.

---

## Single Alembic environment for all modules

**Decision:** One `alembic/versions/` directory for the entire backend, not one per bounded context.

**Rationale:** All bounded contexts share a single PostgreSQL schema in v1. A multi-environment Alembic setup would add complexity (ordering, inter-module dependency chains) with no benefit at this scale. If contexts are ever split into separate services, the migration history can be partitioned at that point.

---

## AllowAll authorization adapter in v1

**Decision:** The v1 `AuthorizationPort` implementation always permits every action. Routes depend on `get_current_actor` and use cases take `actor` in `handle()`, but no checks are enforced.

**Rationale:** The wiring exists so that when the `identity` module lands, only the composition root changes — no route or use case signatures need updating. The app is single-user and self-hosted in v1; multi-user support is a later roadmap item. Building real authorization before identity exists would require faking it in ways that add coupling.

---

## CalVer with a `0.` pre-stable prefix

**Decision:** Version scheme is `0.YYYY.MM.PATCH` until the data model and API stabilise, then `YYYY.MM.PATCH`.

**Rationale:** CalVer communicates the release date naturally for a personal app without semantic versioning overhead. The `0.` prefix signals pre-stable — breaking migrations and API changes are expected — without requiring a formal major-version bump. Dropping the `0.` is the public signal that the schema and API are stable.
