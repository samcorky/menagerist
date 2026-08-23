# Menagerist Backend Architecture

Hexagonal (ports-and-adapters) architecture with DDD, organised as vertical slices by bounded context. This describes the pattern itself - how modules, ports, adapters, and routers relate - not a snapshot of what's currently built.

## Hexagonal architecture

Domain sits at the center and depends on nothing: entities, value objects, and business rules, with zero FastAPI/SQLAlchemy/Pydantic imports. Application wraps domain with use cases and defines **ports** - Python `Protocol`s describing what a use case needs from the outside world (a repository, a clock, an event publisher) without knowing how it's implemented. Adapters come in two directions:

- **Driving (inbound) adapters** call *into* the application layer - API routers, CLI commands, scheduler consumers. They translate an external trigger (an HTTP request, a CLI invocation, a due cron job) into a use-case call.
- **Driven (outbound) adapters** get called *by* the application layer through a port - a SQLAlchemy repository implementing a `NodeRepository` port, an HTTP client implementing a `MetadataEnricher` port.

Dependency direction is the one rule everything else protects:

```
entrypoints  →  adapters  →  application  →  domain
```

Nothing on the right imports anything on the left. Application depends on port interfaces it defines itself, never on the concrete adapter satisfying them. The concrete adapter is chosen and wired in at the composition root (the entrypoint).

## Modules as bounded contexts

The organising principle is *what domain concept this is about* - `graph`, `media`, `search`, `identity` - never *what kind of code this is*. There's no repo-wide `models/`, `services/`, or `routers/`; each module carries its own domain, application, ports, and adapter code:

```
modules/<context>/
├── domain/            # entities, value objects - no framework imports
├── application/       # use cases only - no ports here
├── ports/             # the slice's public contract - one Protocol per file
│   ├── node_repository.py
│   └── unit_of_work.py
└── adapters/
    ├── api/            # FastAPI router - driving adapter
    ├── cli/             # Cyclopts commands, if the context needs one - driving adapter
    └── persistence/     # driven adapters implementing ports/
        ├── models.py
        ├── node_repository.py            # e.g. SqlAlchemyNodeRepository
        ├── in_memory_node_repository.py  # fast-test double, sibling file, no impl/ nesting
        └── unit_of_work.py
```

`ports/` is a standalone package, not colocated inside `application/`, so it's importable by `application/`, `adapters/`, and tests without pulling in SQLAlchemy or FastAPI. In `adapters/persistence/`, a port's real and in-memory implementations are plain sibling files named to match the port they satisfy - no `impl/` subfolder.

A module is created the day its first entity or use case is written, not scaffolded ahead of time. `graph`, modeling nodes and edges, is first in line.

Infra with no domain and nothing swappable behind it lives in `platform/` instead of a module - package metadata, logging config, the database engine. The test: is more than one implementation plausible? If yes (a second repository backend, a second notification channel), it's a port inside a module. If there's exactly one reasonable way to do it, it's a `platform/` primitive.

## Routers are driving adapters, not where logic lives

A router's only job is translating HTTP into a use-case call and the result back into a response. Business rules belong in application/domain, where they're testable without FastAPI running.

```python
@router.post("/nodes", response_model=NodeResponse)
async def create_node(
    payload: CreateNodeRequest,
    use_case: Annotated[CreateNode, Depends(get_create_node_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> NodeResponse:
    node = await use_case.handle(payload.to_command(), actor)
    return NodeResponse.from_domain(node)
```

The router depends on the use case, not on the repository the use case happens to use - that dependency is resolved once, at the composition root, and injected down. CLI commands follow the identical shape: a Cyclopts command is a driving adapter calling the same use case a router would, just triggered from a terminal. A use case never needs a second implementation to be reachable from a second entrypoint.

## Ports carry data, not machinery

A port exposes only what the caller needs, never the internals that produce it. A scheduler port takes a `job_key` string, not a reference to the task registry that resolves it - resolution happens on the inbound side that already owns the registry. If a port signature includes a callable, a registry, or an ORM model, the interface is leaking an adapter's implementation detail into a contract that's supposed to be adapter-agnostic.

Same discipline for ownership boundaries: a use case reconciling system-owned data (schedules, config) and one reconciling user-owned equivalents go through separate ports, even against the same table, so a user-facing edit can't silently touch system-managed state.

## Shared kernel

`shared_kernel/` is a top-level package, a sibling of `modules/` and `platform/`, for domain vocabulary that doesn't belong to one bounded context: the `Identifiable`/`Timestamped`/`SoftDeletable` mixins entities compose from, base exception types (`DomainError`, `NotFoundError`, `ConflictError`, `ValidationError`, `ForbiddenError`) that module-specific errors subclass, and the `Actor`/`AuthorizationPort`/`UnitOfWork`/CQRS Protocols every module depends on. Same purity rule as any module's `domain/` layer: zero framework imports. A mixin or error type genuinely specific to one module stays in that module's `domain/` instead.

`platform/` is the other kind of shared code: infra with exactly one plausible implementation (the database engine, logging config, package metadata). `shared_kernel/` is for domain concepts that cut across contexts; `platform/` is for infra that has no domain shape to begin with.

## Error handling wiring

`register_exception_handlers(app)` is called once inside `create_app()`, mapping `shared_kernel.errors` base types to RFC 9457 (`application/problem+json`) responses:

| Error | Status |
|---|---|
| `ValidationError` | 400 |
| `ForbiddenError` | 403 |
| `NotFoundError` | 404 |
| `ConflictError` | 409 |

A module-specific error like `NodeNotFoundError(NotFoundError)` gets the correct HTTP status for free, purely from subclassing. Routers never carry a `try/except` - the mapping is global, not per-endpoint.

## Persistence and configuration

The async engine, `async_sessionmaker`, and shared declarative `Base` live in `platform/database.py`, configured via `pydantic-settings` (`DATABASE_URL`) - a `platform/` concern by the same one-plausible-implementation test as everything else there.

What's module-specific is which unit of work and use case get constructed from that session factory. That wiring lives in `modules/<context>/adapters/api/dependencies.py`, turning `Depends(get_session_factory)` into `create_graph_uow(session_factory)`, then a `CreateNode` use case. There's no separate per-request session dependency - the unit of work owns session lifecycle itself (see below).

## Local adapters for fast testing

Every port ships an in-memory adapter alongside its real backend adapter, as a first-class citizen rather than a private test-only fake. Application-layer and router-level tests wire the in-memory adapter directly (constructor injection, or FastAPI `dependency_overrides` for router tests) and need no live infrastructure. Only tests checking the *real* adapter's correctness (a `SqlAlchemyNodeRepository` round-tripping through Postgres) are `@pytest.mark.integration` and can be skipped where that infrastructure isn't available.

The `SchedulerPort` will need the same shape later (Postgres/APScheduler/Cron adapters plus an in-memory one), so treat this as a named convention rather than something reinvented per port.

## Domain entities

- Every entity primary key is `uuid7` - time-ordered, so it supports keyset pagination without a separate sort key. List ports paginate as `after: UUID | None` + `limit`, ordered by `id ASC`, not an offset.
- Entities set their own timestamps in domain methods (`datetime.now(UTC)`, alongside `uuid7()` generation) rather than via SQLAlchemy `server_default`/`onupdate`. Timestamping is domain behavior, testable with `freezegun`/`time-machine` without a live database.
- Mixins compose vertically: `Timestamped`, `SoftDeletable(Timestamped)` (a lifecycle change is itself timestamped), concrete entities like `Node(Identifiable, SoftDeletable)`.
- `kw_only=True, eq=False` on every mixin/entity dataclass - keyword-only keeps constructors unambiguous as fields accumulate across mixins; these entities need identity equality (by ID), not structural equality.
- Invariant checks live in `__post_init__` and raise `shared_kernel.errors.ValidationError` (or a module-specific subclass), never a bare `ValueError` - so a violation bubbling up through a use case gets the correct 400 response for free, through the same handler every other domain error goes through.

## Testing mirrors the architecture

Coverage floors: domain 100%, application 90%, infrastructure/API 80% - matching how much of each layer's correctness is structural versus incidental. Domain code has no framework dependencies and is exhaustively unit-testable; adapters carry real sessions/HTTP/external services where 100% is impractical or low-signal. `@pytest.mark.integration` separates the fast domain-heavy loop from the slower suite touching real adapters.

`backend/tests/` mirrors `src/app/modules/<context>/{domain,application,adapters}` directory-for-directory, plus `tests/architecture/`: an `archunitpython` suite encoding the dependency-direction rule itself (domain may not depend on application/adapters/entrypoints, application may not depend on adapters/entrypoints, adapters may not depend on entrypoints). No I/O, always runs, catches a boundary violation before it becomes a design problem.

## Migrations

One Alembic environment, one `alembic/versions/` directory, for the whole backend - not one per module. All bounded contexts share a single Postgres schema in v1. Each module's SQLAlchemy models register on the shared `Base` from `platform/database.py`; `alembic/env.py` imports every module's `adapters/persistence/models.py` explicitly so their tables exist on `Base.metadata` before autogenerate runs.

## Running things

Backend tests, migrations, and quality checks run as `poe` tasks from the workspace root - `poe test-backend`, `poe test-backend-integration`, `poe migrate`, `poe lint-backend`, `poe typecheck-backend`, etc. Full task list in the root `pyproject.toml`.

## Unit of work: a shared Protocol, not a per-module subclass

`shared_kernel/unit_of_work.py` defines `UnitOfWork[TRepos]` as a `Protocol` - `__aenter__() -> TRepos`, `__aexit__`, `commit()` - satisfied structurally by two implementations written once and reused by every module:

- `platform/unit_of_work.py::SqlAlchemySessionUnitOfWork[TRepos]` - opens a session from an `async_sessionmaker`, owns begin/rollback-on-exception/always-close/commit. Lives in `platform/` for the same reason `platform/database.py` does: exactly one plausible implementation.
- `shared_kernel/unit_of_work.py::InMemoryUnitOfWork[TRepos]` - wraps an already-built repo bundle directly. `__aenter__` just returns what it was given, so there's no session to open or spoof. `.committed`/`.rolled_back` flags let a test assert a use case reached (or correctly avoided) its commit point.

A module contributes a repo-bundle dataclass (`modules/graph/ports/unit_of_work.py::GraphRepos(nodes, edges)`) and a `GraphUnitOfWork = UnitOfWork[GraphRepos]` alias next to it, plus two one-line factories in `adapters/persistence/unit_of_work.py` - `create_graph_uow(session_factory)` and `create_in_memory_graph_uow(repos)` - each constructing one of the two shared implementations around a `GraphRepos`. No module writes `__aenter__`/`__aexit__`/`commit` itself.

A single central unit of work listing every module's repositories was rejected: it couples every module's use cases to every other module's repositories, and implies transactions spanning bounded contexts, which DDD treats as the wrong boundary. Cross-context consistency is handled by referencing IDs and accepting eventual consistency. A second module gets its own `Repos` dataclass and factories on the same two shared implementations, not a slot added to `GraphRepos`.

This also decouples the transaction from the HTTP request/response cycle - the same use case is reachable from a CLI command or a scheduled job, neither of which has a "request" to hang a commit off. The use case owns the commit via the unit of work it's given, so the transaction boundary travels with it regardless of which driving adapter called it.

**Commands take the unit of work; queries take a plain repository.** `CreateNode`/`CreateEdge` depend on `GraphUnitOfWork` and call `await uow.commit()` once their invariants pass. `GetNode`/`ListNodes`/`GetEdge` are read-only and depend on `NodeRepository`/`EdgeRepository` directly - a read has no commit boundary to own.

## CQRS is a typing convention, not a dispatcher

`shared_kernel/cqrs.py` defines two generic Protocols, `CommandHandler[TCommand, TResult]` and `QueryHandler[TQuery, TResult]`, each with `handle(self, command_or_query, actor: Actor) -> TResult`. Every use case gets a matching `*Command`/`*Query` dataclass (`CreateNodeCommand`, `GetNodeQuery`, ...) and implements the corresponding Protocol, so `mypy --strict` verifies every use case in every module is shaped the same way.

`actor` is a `handle()` parameter, not a field on the command/query - it travels alongside the unit of work/repository rather than being baked into the "what to do" data.

There's no bus or mediator between a router/CLI command and the use case it calls - the router calls the use case directly, as shown above. A bus with pipeline behaviors would give a single seam for cross-cutting concerns (logging, authorization) applied uniformly, but nothing here needs that uniformity enforced yet. The typed-handler convention, plus every handler already taking an `actor`, is a prerequisite for a bus regardless, so this doesn't foreclose adding one later.

## Cross-cutting concerns

**Permissions - wired, not enforced.** `shared_kernel/actor.py::Actor` (an id plus opaque `roles`) and `shared_kernel/authorization.py::AuthorizationPort` (`check(actor, action) -> None`, raising `ForbiddenError`) live in `shared_kernel/` since no bounded context owns authorization yet. The v1 concrete adapter, `entrypoints/api/shared/authorization.py::AllowAllAuthorizationAdapter`, always permits, and is wired at the composition root (`entrypoints/api/shared/dependencies.py`) rather than in `shared_kernel/` or a module, since it's a real adapter with no bounded-context owner yet. Routes depend on `get_current_actor` (v1: a fixed single-owner `Actor`); use cases take `actor` in `handle()` regardless of whether anything is actually checked. When the `identity` module lands (the OIDC roadmap step), only `get_current_actor` and the `AuthorizationPort` adapter get swapped - no route or use case signature changes, since they were only ever written against the port.

**Backups - deferred.** Not designed yet. Whatever shape it takes (infra-level `pg_dump`, an app-level export/import module composing each slice's own export port, or both) should reuse the `Actor`/`AuthorizationPort` seam above unmodified, since exporting data is itself an actor-attributed action - but the design is future work, not scaffolded ahead of time.
